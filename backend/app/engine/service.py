"""Service layer: turns engine results into API payloads, with caching.

All functions are synchronous and CPU-bound; the API runs them in a worker
thread (never on the event loop) behind a small concurrency limiter.
"""

from __future__ import annotations

import hashlib
import json
import threading
import time
from collections import OrderedDict
from typing import Any

import numpy as np
import pandas as pd

from app.core.errors import CriseesError
from app.engine import accessibility as acc_mod
from app.engine.context import RegionEngine, get_engine
from app.engine.demand import priority_weights, sensitivity, tract_demand
from app.engine.network import CLASS_SPEED_KPH, POSTED_SPEED_RANGE, WALK_SPEED_M_PER_MIN
from app.engine.optimization import Solution, inputs_from_state, solve
from app.engine.params import (
    AccessibilityRequest,
    AccessParams,
    CompareRequest,
    DemandParams,
    EquityWeights,
    OptimizeRequest,
    Resources,
    ScenarioEvaluateRequest,
    ScenarioSpec,
    SolverSettings,
)
from app.engine.scenarios import PRESET_DESCRIPTIONS, PRESETS, resolve, scenario_id
from app.services.repository import DataRepository
from app.services.serialization import clean_value, geometry_to_geojson

DISCLAIMER = (
    "Planning simulation with HYPOTHETICAL flood closures, participation rates, fleets and shelter capacities. "
    "Results are modelled outcomes, not demonstrated real-world impact. Mapped facilities are not verified "
    "evacuation shelters. FEMA data covers only part of the study area; roads outside it have unknown flood status."
)


class ScenarioNotFoundError(CriseesError):
    status_code = 404
    code = "scenario_not_found"


class UnknownPresetError(CriseesError):
    status_code = 400
    code = "unknown_scenario_preset"


class EngineBusyError(CriseesError):
    status_code = 503
    code = "engine_busy"


class OptimizationFailedError(CriseesError):
    status_code = 422
    code = "optimization_failed"


# --------------------------------------------------------------- concurrency
_jobs = threading.BoundedSemaphore(2)


class job_slot:
    """Limit concurrent CPU-heavy jobs; fail fast with 503 rather than queue forever."""

    def __init__(self, wait_s: float = 60) -> None:
        self.wait_s = wait_s

    def __enter__(self) -> None:
        if not _jobs.acquire(timeout=self.wait_s):
            raise EngineBusyError("The analysis engine is busy; retry shortly.", retry_after_s=5)

    def __exit__(self, *exc: object) -> None:
        _jobs.release()


# ------------------------------------------------------------------ caching
_results: "OrderedDict[str, Any]" = OrderedDict()
_results_lock = threading.Lock()
_scenarios: dict[str, dict] = {}  # scenario_id -> {region, spec}


def _cache_key(kind: str, region_id: str, stamp: str, payload: dict) -> str:
    raw = json.dumps({"k": kind, "r": region_id, "s": stamp, "p": payload}, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode()).hexdigest()


def _cached(key: str, fn):  # type: ignore[no-untyped-def]
    with _results_lock:
        if key in _results:
            _results.move_to_end(key)
            hit = dict(_results[key])
            hit["cache"] = "hit"
            return hit
    value = fn()
    value["cache"] = "miss"
    with _results_lock:
        _results[key] = value
        while len(_results) > 32:
            _results.popitem(last=False)
    return value


def clear_caches() -> None:
    with _results_lock:
        _results.clear()
    _scenarios.clear()
    acc_mod.clear_cache()


def _resolve(spec: ScenarioSpec | str) -> ScenarioSpec:
    try:
        return resolve(spec)
    except KeyError:
        raise UnknownPresetError(f"Unknown scenario preset '{spec}'.", available=sorted(PRESETS)) from None


def _register(eng: RegionEngine, spec: ScenarioSpec) -> str:
    sid = scenario_id(eng.region.region_id, eng.stamp, spec)
    _scenarios[sid] = {"region_id": eng.region.region_id, "spec": spec}
    return sid


def _f(v: Any, nd: int = 3) -> Any:
    v = clean_value(v)
    if isinstance(v, float):
        return round(v, nd) if np.isfinite(v) else None
    return v


# ---------------------------------------------------------------- scenarios
def list_presets() -> list[dict]:
    return [{"name": k, "description": PRESET_DESCRIPTIONS[k], "spec": v.model_dump(mode="json")}
            for k, v in PRESETS.items()]


def evaluate_scenario(repo: DataRepository, region_id: str, req: ScenarioEvaluateRequest) -> dict:
    spec = _resolve(req.scenario)
    eng = get_engine(repo, region_id)
    sid = _register(eng, spec)
    key = _cache_key("scenario", region_id, eng.stamp, {"spec": spec.model_dump(mode="json"),
                                                         "access": req.access.model_dump(mode="json"),
                                                         "geo": req.include_closures_geojson})

    def run() -> dict:
        t0 = time.perf_counter()
        cell = DemandParams().origin_cell_m
        base = acc_mod.scenario_state(eng, PRESETS["baseline"], req.access, cell)
        st = acc_mod.scenario_state(eng, spec, req.access, cell)
        closed = st.closures.closed
        net = eng.net
        seg_closed = np.unique(net.segment_id[closed])
        first = ~pd.Series(net.segment_id).duplicated().to_numpy()
        closed_len = float(net.length_m[first & closed].sum()) / 1000
        o = st.origins.table
        near_b, near_s = base.drive_origin_nearest_shelter, st.drive_origin_nearest_shelter
        lost = np.isfinite(near_b) & ~np.isfinite(near_s)
        both = np.isfinite(near_b) & np.isfinite(near_s)
        demand = tract_demand(eng.vehicle_access, eng.demographics, DemandParams())
        d_o = demand.set_index("geoid")["demand_est"].reindex(o["geoid"]).fillna(0).to_numpy() * o["share"].to_numpy()
        thr = max(req.access.drive_thresholds_min)
        hubs_leg_b = int((np.isfinite(base.drive_hub_shelter).any(axis=1)).sum())
        hubs_leg_s = int((np.isfinite(st.drive_hub_shelter).any(axis=1)).sum())
        out = {
            "scenario_id": sid,
            "region_id": region_id,
            "spec": spec.model_dump(mode="json"),
            "description": PRESET_DESCRIPTIONS.get(spec.name, "Custom scenario."),
            "closures": {
                "closed_directed_edges": int(closed.sum()),
                "closed_segments": int(len(seg_closed)),
                "closed_length_km": round(closed_len, 2),
                "closed_segments_by_rule": st.closures.by_rule,
                "unknown_coverage_segments": st.closures.unknown_segments,
                "unknown_coverage_length_km": st.closures.unknown_length_km,
                "unknown_coverage_policy": spec.unknown_coverage_policy,
                "note": "Closures are hypothetical; exposure is FEMA regulatory. Roads outside FEMA coverage are "
                        "UNKNOWN (not safe) and are not closed under 'no_inference'.",
            },
            "network": {"baseline": base.components, "scenario": st.components},
            "access_change": {
                "origins": int(len(o)),
                "origins_losing_all_drive_routes_to_shelters": int(lost.sum()),
                "demand_at_origins_losing_drive_routes": round(float(d_o[lost].sum()), 1),
                "mean_drive_min_to_nearest_shelter_baseline": _f(np.average(near_b[both], weights=d_o[both] + 1e-12) if both.any() else None, 2),
                "mean_drive_min_to_nearest_shelter_scenario": _f(np.average(near_s[both], weights=d_o[both] + 1e-12) if both.any() else None, 2),
                "p90_drive_min_increase": _f(np.percentile((near_s - near_b)[both], 90) if both.any() else None, 2),
                f"mean_shelters_within_{thr:g}_min_baseline": _f(float(np.average(base.drive_origin_shelter_counts[thr], weights=d_o + 1e-12)), 2),
                f"mean_shelters_within_{thr:g}_min_scenario": _f(float(np.average(st.drive_origin_shelter_counts[thr], weights=d_o + 1e-12)), 2),
                "hubs_with_drive_route_to_a_shelter_baseline": hubs_leg_b,
                "hubs_with_drive_route_to_a_shelter_scenario": hubs_leg_s,
                "shelters_assumed": int(len(st.dest.shelters)),
                "candidate_hubs": int(len(st.dest.hubs)),
            },
            "speed_model": eng.net.speed_summary(),
            "timings_s": {**st.timings_s, "total": round(time.perf_counter() - t0, 3)},
            "provenance": {"data_generated_at": eng.stamp, "scenario_id_inputs": "sha256(region, data stamp, spec)",
                           "deterministic": True},
            "disclaimer": DISCLAIMER,
        }
        if req.include_closures_geojson:
            out["closures_geojson"] = closures_geojson(repo, region_id, sid, limit=2000, offset=0)
        return out

    with job_slot():
        return _cached(key, run)


def closures_geojson(repo: DataRepository, region_id: str, sid: str, limit: int, offset: int) -> dict:
    entry = _scenarios.get(sid)
    if entry is None:  # survive restarts for presets: their ids are deterministic
        eng0 = get_engine(repo, region_id)
        for spec in PRESETS.values():
            if scenario_id(region_id, eng0.stamp, spec) == sid:
                entry = {"region_id": region_id, "spec": spec}
                _scenarios[sid] = entry
    if entry is None or entry["region_id"] != region_id:
        raise ScenarioNotFoundError(
            f"Scenario '{sid}' is not known. Evaluate it first with POST /scenarios/evaluate.", scenario_id=sid)
    eng = get_engine(repo, region_id)
    from app.engine.scenarios import compute_closures

    cr = compute_closures(eng, entry["spec"])
    net = eng.net
    first = ~pd.Series(net.segment_id).duplicated().to_numpy()
    idx = np.flatnonzero(cr.closed & first)
    edges = repo.load(region_id, "road_edges")
    page = idx[offset: offset + limit]
    exp = eng.exposure
    feats = []
    for i in page:
        row = edges.iloc[i]
        feats.append({"type": "Feature", "id": row["edge_id"], "geometry": geometry_to_geojson(row.geometry),
                      "properties": {"edge_id": row["edge_id"], "road_class": row["road_class"],
                                     "name": clean_value(row["name"]), "length_m": round(float(row["length_m"]), 1),
                                     "len_in_1pct_m": _f(exp["len_in_1pct_m"].iat[i], 1),
                                     "dist_to_1pct_m": _f(exp["dist_to_1pct_m"].iat[i], 1),
                                     "both_directions_closed": True}})
    return {"type": "FeatureCollection", "scenario_id": sid, "features": feats,
            "page": {"total": int(len(idx)), "limit": limit, "offset": offset, "returned": len(feats),
                     "next_offset": offset + limit if offset + limit < len(idx) else None},
            "provenance": "derived", "evidence_type": "simulated"}


# ------------------------------------------------------------ accessibility
def _tract_geoms(eng: RegionEngine, simplify_m: float | None) -> dict[str, Any]:
    t = eng.tracts.set_index("geoid")
    geoms = t.geometry
    if simplify_m:
        geoms = t.to_crs(eng.region.analysis_crs).geometry.simplify(simplify_m).to_crs(4326)
    return {g: geometry_to_geojson(geom, precision=5) for g, geom in geoms.items()}


def analyze_accessibility(repo: DataRepository, region_id: str, req: AccessibilityRequest) -> dict:
    spec = _resolve(req.scenario)
    eng = get_engine(repo, region_id)
    sid = _register(eng, spec)
    key = _cache_key("access", region_id, eng.stamp, req.model_dump(mode="json"))

    def run() -> dict:
        t0 = time.perf_counter()
        table, summary, _, st = acc_mod.analyze(eng, spec, req.access, req.demand)
        geoms = _tract_geoms(eng, req.simplify_m) if req.include_geometry else {}
        names = eng.tracts.set_index("geoid")["name"]
        feats = []
        for row in table.to_dict("records"):
            props = {k: _f(v, 4) for k, v in row.items()}
            props["name"] = names.get(row["geoid"])
            feats.append({"type": "Feature", "id": row["geoid"], "geometry": geoms.get(row["geoid"]),
                          "properties": props})
        return {"type": "FeatureCollection", "scenario_id": sid, "region_id": region_id,
                "spec": spec.model_dump(mode="json"), "summary": summary, "features": feats,
                "units": {"drive": "minutes", "walk": "metres (walk_min_* in minutes at "
                          f"{WALK_SPEED_M_PER_MIN:g} m/min)", "shares": "0-1 of tract estimated demand"},
                "method_notes": [
                    "Walk distances use the drive network without motorways/trunks, undirected, as a PROXY for a "
                    "pedestrian network.",
                    "Tract values are averages over sub-tract origins weighted by residential street length.",
                    "Unreachable = null, never 0. Shelters are ASSUMED facilities, not designated shelters.",
                ],
                "timings_s": {"total": round(time.perf_counter() - t0, 3)}, "disclaimer": DISCLAIMER}

    with job_slot():
        return _cached(key, run)


# --------------------------------------------------------------- optimise
def _demand_and_weights(eng: RegionEngine, dp: DemandParams, wp: EquityWeights) -> tuple[pd.DataFrame, pd.DataFrame]:
    demand = tract_demand(eng.vehicle_access, eng.demographics, dp)
    return demand, priority_weights(eng.demographics, demand, wp)


def _terciles(weights_equity: pd.DataFrame) -> pd.Series:
    """Priority tercile per tract from equity weights (1=lowest, 3=highest)."""
    r = weights_equity.set_index("geoid")["weight_raw"].rank(method="first")
    return pd.qcut(r, 3, labels=[1, 2, 3]).astype(int)


def summarize_solution(eng: RegionEngine, st: acc_mod.ScenarioState, sol: Solution, demand: pd.DataFrame,
                       weights: pd.DataFrame, equity_w: pd.DataFrame, res: Resources) -> dict:
    o = st.origins.table
    D = (demand.set_index("geoid")["demand_est"].reindex(o["geoid"]).fillna(0).to_numpy() * o["share"].to_numpy())
    served_hub = np.bincount(sol.x["o"].astype(int), weights=sol.x["persons"], minlength=len(o)) if len(sol.x) else np.zeros(len(o))
    served_walk = np.bincount(sol.g["o"].astype(int), weights=sol.g["persons"], minlength=len(o)) if len(sol.g) else np.zeros(len(o))
    per_o = pd.DataFrame({"geoid": o["geoid"], "demand": D, "served_hub": served_hub, "served_walk": served_walk,
                          "unmet": sol.u})
    tr = per_o.groupby("geoid").sum()
    w_run = weights.set_index("geoid")["weight"]
    w_eq = equity_w.set_index("geoid")["weight"]
    tr["weight"] = w_run.reindex(tr.index)
    tr["equity_weight"] = w_eq.reindex(tr.index)
    tr["served"] = tr["served_hub"] + tr["served_walk"]
    tr["coverage"] = np.where(tr["demand"] > 0, tr["served"] / tr["demand"].where(tr["demand"] > 0), np.nan)
    tr["priority_tercile"] = _terciles(equity_w).reindex(tr.index)
    total_d = float(tr["demand"].sum())
    served = float(tr["served"].sum())
    dist = {}
    for k, grp in tr.groupby("priority_tercile"):
        dsum = float(grp["demand"].sum())
        dist[f"tercile_{k}"] = {"tracts": int(len(grp)), "demand": round(dsum, 1),
                                "served": round(float(grp["served"].sum()), 1),
                                "coverage": round(float(grp["served"].sum()) / dsum, 4) if dsum else None}
    hubs = st.dest.hubs
    shel = st.dest.shelters
    active = [h for h, v in sol.y.items() if v > 0.5]
    hub_rows = []
    for h in sorted(active, key=lambda h: hubs.iloc[h]["hub_id"]):
        legs = sol.f[sol.f["h"] == h]
        assigned = float(sol.x.loc[sol.x["h"] == h, "persons"].sum()) if len(sol.x) else 0.0
        hrow = hubs.iloc[h]
        walk = sol.x[sol.x["h"] == h]
        hub_rows.append({
            "hub_id": hrow["hub_id"], "facility_id": hrow["facility_id"], "name": clean_value(hrow["name"]),
            "category": hrow["category"], "lon": float(hrow["lon"]), "lat": float(hrow["lat"]),
            "flood_status": hrow["flood_status"], "persons_assigned": round(assigned, 1),
            "capacity_utilization": round(assigned / res.hub_capacity, 4) if res.hub_capacity else None,
            "mean_walk_m": round(float(np.average(walk["walk_m"], weights=walk["persons"])), 1) if len(walk) and walk["persons"].sum() > 0 else None,
            "origins_served": int(walk["o"].nunique()),
            "legs": [{"shelter_id": shel.iloc[int(r.s)]["facility_id"], "shelter_name": clean_value(shel.iloc[int(r.s)]["name"]),
                      "persons": round(float(r.persons), 1), "trips": int(round(r.trips)),
                      "drive_min": round(float(r.drive_min), 2), "round_trip_min": round(float(r.round_trip_min), 2)}
                     for r in legs.itertuples()],
        })
    shel_load = pd.concat([sol.f.groupby("s")["persons"].sum() if len(sol.f) else pd.Series(dtype=float),
                           sol.g.groupby("s")["persons"].sum() if len(sol.g) else pd.Series(dtype=float)]).groupby(level=0).sum()
    shelter_rows = [{"facility_id": shel.iloc[int(s)]["facility_id"], "name": clean_value(shel.iloc[int(s)]["name"]),
                     "lon": float(shel.iloc[int(s)]["lon"]), "lat": float(shel.iloc[int(s)]["lat"]),
                     "flood_status": shel.iloc[int(s)]["flood_status"], "persons": round(float(v), 1),
                     "capacity_utilization": round(float(v) / res.shelter_capacity, 4) if res.shelter_capacity else None}
                    for s, v in shel_load.items() if v > 1e-6]
    trips = float(sol.f["trips"].sum()) if len(sol.f) else 0.0
    bus_persons = float(sol.f["persons"].sum()) if len(sol.f) else 0.0
    totals = {
        "demand_est": round(total_d, 1),
        "served": round(served, 1),
        "served_via_hubs": round(float(tr["served_hub"].sum()), 1),
        "served_by_direct_walk_to_shelter": round(float(tr["served_walk"].sum()), 1),
        "unmet": round(float(tr["unmet"].sum()), 1),
        "coverage": round(served / total_d, 4) if total_d else None,
        "weighted_unmet_run_weights": round(float((tr["unmet"] * tr["weight"]).sum()), 1),
        "weighted_unmet_equity_weights": round(float((tr["unmet"] * tr["equity_weight"]).sum()), 1),
        "weighted_coverage_equity_weights": round(float((tr["served"] * tr["equity_weight"]).sum() / (tr["demand"] * tr["equity_weight"]).sum()), 4) if total_d else None,
        "active_hubs": len(active),
        "vehicle_trips": int(round(trips)),
        "vehicle_minutes_used": sol.constraint_check.get("vehicle_minutes_used"),
        "vehicle_minutes_available": res.vehicles * res.horizon_min,
        "fleet_utilization": round(sol.constraint_check.get("vehicle_minutes_used", 0) / (res.vehicles * res.horizon_min), 4) if res.vehicles else None,
        "mean_walk_m_served_via_hub": round(float(np.average(sol.x["walk_m"], weights=sol.x["persons"])), 1) if len(sol.x) and sol.x["persons"].sum() > 0 else None,
        "mean_bus_drive_min": round(float(np.average(sol.f["drive_min"], weights=sol.f["persons"])), 2) if bus_persons > 0 else None,
        "mean_seat_occupancy": round(bus_persons / (trips * res.vehicle_capacity), 4) if trips else None,
    }
    tracts = [{"geoid": g, "demand": round(float(r.demand), 2), "served_via_hubs": round(float(r.served_hub), 2),
               "served_by_direct_walk": round(float(r.served_walk), 2), "unmet": round(float(r.unmet), 2),
               "coverage": _f(r.coverage, 4), "weight": _f(r.weight, 4), "priority_tercile": int(r.priority_tercile)}
              for g, r in tr.iterrows()]
    near = 0.999
    binding = {
        "hub_budget_used": f"{len(active)}/{res.max_active_hubs}",
        "hubs_at_capacity": sum(1 for h in hub_rows if h["capacity_utilization"] and h["capacity_utilization"] >= near),
        "shelters_at_capacity": sum(1 for r in shelter_rows if r["capacity_utilization"] and r["capacity_utilization"] >= near),
        "shelters_used": len(shelter_rows),
        "fleet_time_binding": bool(res.vehicles and totals["fleet_utilization"] is not None and totals["fleet_utilization"] >= near),
        "demand_beyond_walk_catchment_share": round(float(np.where(
            (st.walk_origin_hub.min(axis=1) if st.walk_origin_hub.shape[1] else np.full(len(o), np.inf)) > 1e12, 0, 0).sum()), 4),
    }
    walk_ok = np.zeros(len(o), bool)
    if st.walk_origin_hub.shape[1]:
        walk_ok |= st.walk_origin_hub.min(axis=1) <= sol.screening.get("walk_max_m", np.inf)
    if st.walk_origin_shelter.shape[1]:
        walk_ok |= st.walk_origin_shelter.min(axis=1) <= sol.screening.get("walk_max_m", np.inf)
    binding["demand_without_any_walkable_hub_or_shelter"] = round(float(D[~walk_ok].sum()), 1)
    binding.pop("demand_beyond_walk_catchment_share")
    return {"totals": totals, "binding_constraints": binding, "distribution_by_priority_tercile": dist,
            "hubs": hub_rows, "shelters": shelter_rows, "tracts": tracts}


def _solver_block(sol: Solution, settings: SolverSettings) -> dict:
    return {"status": sol.status, "message": sol.message, "objective": _f(sol.objective, 4), "mip_gap": _f(sol.mip_gap, 6),
            "dual_bound": _f(sol.dual_bound, 4), "solve_seconds": sol.solve_seconds, "build_seconds": sol.build_seconds,
            "model_size": sol.model_size, "screening": sol.screening, "engine": "HiGHS via scipy.optimize.milp",
            "settings": settings.model_dump(mode="json"),
            "optimality_claim": {"optimal": "Proven optimal.",
                                 "optimal_within_gap": f"Optimal within relative gap {sol.mip_gap} (proven bound).",
                                 "time_limit_feasible": "Time limit reached: feasible but NOT proven optimal.",
                                 }.get(sol.status, "No optimality claim.")}


def run_optimization(eng: RegionEngine, spec: ScenarioSpec, demand_p: DemandParams, weights_p: EquityWeights,
                     access: AccessParams, res: Resources, solver: SolverSettings,
                     fixed_hubs: list[str] | None = None) -> dict:
    st = acc_mod.scenario_state(eng, spec, access, demand_p.origin_cell_m)
    demand, weights = _demand_and_weights(eng, demand_p, weights_p)
    _, equity_w = _demand_and_weights(eng, demand_p, EquityWeights(**{**weights_p.model_dump(), "mode": "equity"}))
    inp = inputs_from_state(st, demand, weights)
    sol = solve(inp, access, res, solver, fixed_hubs=fixed_hubs)
    if sol.status in ("infeasible", "unbounded", "solver_error", "time_limit_no_solution"):
        raise OptimizationFailedError(f"Optimisation did not produce a solution: {sol.status}.",
                                      status=sol.status, solver_message=sol.message, model_size=sol.model_size)
    out = summarize_solution(eng, st, sol, demand, weights, equity_w, res)
    out["solver"] = _solver_block(sol, solver)
    out["constraint_check"] = sol.constraint_check
    out["scenario_id"] = _register(eng, spec)
    out["weights_used"] = weights_p.model_dump(mode="json")
    out["_hub_ids"] = [h["hub_id"] for h in out["hubs"]]
    return out


def optimize(repo: DataRepository, region_id: str, req: OptimizeRequest) -> dict:
    spec = _resolve(req.scenario)
    eng = get_engine(repo, region_id)
    key = _cache_key("optimize", region_id, eng.stamp, req.model_dump(mode="json"))

    def run() -> dict:
        t0 = time.perf_counter()
        out = run_optimization(eng, spec, req.demand, req.weights, req.access, req.resources, req.solver)
        out.pop("_hub_ids", None)
        if req.include_geometry:
            geoms = _tract_geoms(eng, 25)
            out["tracts_geojson"] = {"type": "FeatureCollection", "features": [
                {"type": "Feature", "id": t["geoid"], "geometry": geoms.get(t["geoid"]), "properties": t}
                for t in out["tracts"]]}
            out["hubs_geojson"] = {"type": "FeatureCollection", "features": [
                {"type": "Feature", "id": h["hub_id"], "geometry": {"type": "Point", "coordinates": [h["lon"], h["lat"]]},
                 "properties": {k: v for k, v in h.items() if k not in ("lon", "lat")}} for h in out["hubs"]]}
        out.update({"region_id": region_id, "scenario": spec.model_dump(mode="json"),
                    "assumptions": {"demand": req.demand.model_dump(mode="json"), "access": req.access.model_dump(mode="json"),
                                    "resources": req.resources.model_dump(mode="json")},
                    "timings_s": {"total": round(time.perf_counter() - t0, 3)}, "disclaimer": DISCLAIMER})
        return out

    with job_slot():
        return _cached(key, run)


# --------------------------------------------------------------- compare
def _case(name: str, label: str, result: dict) -> dict:
    return {"case": name, "label": label, "scenario_id": result["scenario_id"], "totals": result["totals"],
            "distribution_by_priority_tercile": result["distribution_by_priority_tercile"],
            "binding_constraints": result["binding_constraints"],
            "solver_status": result["solver"]["status"], "mip_gap": result["solver"]["mip_gap"],
            "constraint_check_feasible": result["constraint_check"]["feasible"],
            "active_hub_ids": result["_hub_ids"]}


def compare(repo: DataRepository, region_id: str, req: CompareRequest) -> dict:
    spec = _resolve(req.disrupted_scenario)
    eng = get_engine(repo, region_id)
    key = _cache_key("compare", region_id, eng.stamp, req.model_dump(mode="json"))

    def run() -> dict:
        t0 = time.perf_counter()
        base = PRESETS["baseline"]
        none = Resources(**{**req.resources.model_dump(), "max_active_hubs": 0, "vehicles": 0})
        eq = EquityWeights(**{**req.weights.model_dump(), "mode": "equity"})
        flat = EquityWeights(**{**req.weights.model_dump(), "mode": "equal"})
        args = (req.demand,)
        r_a = run_optimization(eng, base, *args, eq, req.access, none, req.solver)
        r_b = run_optimization(eng, spec, *args, eq, req.access, none, req.solver)
        r_c = run_optimization(eng, spec, *args, eq, req.access, req.resources, req.solver)
        r_d = run_optimization(eng, spec, *args, flat, req.access, req.resources, req.solver)
        cases = [
            _case("baseline_no_intervention", "Baseline network, no pickup hubs or vehicles (walk directly to an assumed shelter only)", r_a),
            _case("disrupted_no_intervention", "Disrupted network, no added intervention", r_b),
            _case("disrupted_equity_optimized", "Disrupted network, hubs + vehicles optimised with equity weights", r_c),
            _case("disrupted_equal_weight_optimized", "Disrupted network, hubs + vehicles optimised with equal weights", r_d),
        ]
        if req.include_robustness_case:
            r_plan = run_optimization(eng, base, *args, eq, req.access, req.resources, req.solver)
            r_e = run_optimization(eng, spec, *args, eq, req.access, req.resources, req.solver,
                                   fixed_hubs=r_plan["_hub_ids"])
            cases.append(_case("baseline_plan_under_disruption",
                               "Hubs chosen for the baseline network, flows re-optimised on the disrupted network", r_e))
        by = {c["case"]: c["totals"] for c in cases}

        def delta(a: str, b: str, k: str) -> float | None:
            va, vb = by[a].get(k), by[b].get(k)
            return None if va is None or vb is None else round(vb - va, 4)

        keys = ["served", "unmet", "coverage", "weighted_unmet_equity_weights", "weighted_coverage_equity_weights"]
        deltas = {
            "disruption_effect (disrupted_no_intervention - baseline_no_intervention)":
                {k: delta("baseline_no_intervention", "disrupted_no_intervention", k) for k in keys},
            "intervention_effect (disrupted_equity_optimized - disrupted_no_intervention)":
                {k: delta("disrupted_no_intervention", "disrupted_equity_optimized", k) for k in keys},
            "equity_vs_equal (disrupted_equity_optimized - disrupted_equal_weight_optimized)":
                {k: delta("disrupted_equal_weight_optimized", "disrupted_equity_optimized", k) for k in keys},
        }
        if req.include_robustness_case:
            deltas["reoptimization_value (disrupted_equity_optimized - baseline_plan_under_disruption)"] = \
                {k: delta("baseline_plan_under_disruption", "disrupted_equity_optimized", k) for k in keys}
        findings = _findings(by, cases)
        access_table, access_summary, _, _ = acc_mod.analyze(eng, spec, req.access, req.demand)
        return {"region_id": region_id, "disrupted_scenario": spec.model_dump(mode="json"),
                "scenario_id": _register(eng, spec), "cases": cases, "deltas": deltas, "findings": findings,
                "accessibility_change": access_summary,
                "most_affected_tracts": access_table.sort_values("demand_weighted_walk_access_loss", ascending=False)
                .head(10)[["geoid", "demand_est", "demand_weighted_walk_access_loss", "demand_newly_without_drive_route",
                           "delta_drive_min_to_nearest_shelter"]].map(lambda v: _f(v, 3)).to_dict("records"),
                "identical_inputs": {"demand": req.demand.model_dump(mode="json"), "access": req.access.model_dump(mode="json"),
                                     "resources": req.resources.model_dump(mode="json"), "weights": req.weights.model_dump(mode="json"),
                                     "solver": req.solver.model_dump(mode="json")},
                "timings_s": {"total": round(time.perf_counter() - t0, 3)}, "disclaimer": DISCLAIMER}

    with job_slot(wait_s=120):
        return _cached(key, run)


def _findings(by: dict, cases: list[dict]) -> list[str]:
    out = []
    a, b = by["baseline_no_intervention"], by["disrupted_no_intervention"]
    c, d = by["disrupted_equity_optimized"], by["disrupted_equal_weight_optimized"]
    out.append(f"Disruption changes walk-only service from {a['served']:,.0f} to {b['served']:,.0f} persons "
               f"(modelled).")
    gain = c["served"] - b["served"]
    if gain > 0.5:
        out.append(f"Optimised hubs and vehicles serve {gain:,.0f} more persons than no intervention under the same "
                   f"disruption; {c['unmet']:,.0f} of {c['demand_est']:,.0f} remain unmet.")
    else:
        out.append("The intervention did not increase modelled service under this disruption and budget.")
    if c["weighted_unmet_equity_weights"] < d["weighted_unmet_equity_weights"] - 0.5:
        out.append(f"Equity weighting lowers priority-weighted unmet demand by "
                   f"{d['weighted_unmet_equity_weights'] - c['weighted_unmet_equity_weights']:,.1f} "
                   f"versus equal weighting, while total served changes by {c['served'] - d['served']:+,.1f}.")
    else:
        out.append("Equity weighting produced no material difference in priority-weighted unmet demand versus "
                   "equal weighting for these inputs.")
    for case in cases:
        if case["solver_status"] not in ("optimal", "optimal_within_gap"):
            out.append(f"Case {case['case']} ended with solver status {case['solver_status']}; not proven optimal.")
    return out


# ------------------------------------------------------------ demand / docs
def demand_estimates(repo: DataRepository, region_id: str, dp: DemandParams, wp: EquityWeights) -> dict:
    eng = get_engine(repo, region_id)
    demand, weights = _demand_and_weights(eng, dp, wp)
    merged = demand.merge(weights, on="geoid")
    records = [{k: _f(v, 4) if not isinstance(v, list) else v for k, v in r.items()} for r in merged.to_dict("records")]
    sens = sensitivity(eng.vehicle_access, eng.demographics, [0.25, 0.5, 0.75, 1.0], [4.0, 4.5, 5.0])
    return {"region_id": region_id, "params": dp.model_dump(mode="json"), "weights": wp.model_dump(mode="json"),
            "total_persons_zero_vehicle_est": round(float(demand["persons_zero_vehicle_est"].sum()), 1),
            "total_demand_est": round(float(demand["demand_est"].sum()), 1),
            "tracts": records, "sensitivity": sens,
            "definitions": {
                "observed": ["households_no_vehicle", "hh_no_vehicle_1p..4p_plus (ACS B08201)", "total_population"],
                "estimated": ["persons_zero_vehicle_est", "demand_est"],
                "priority": ["rank_poverty", "rank_disability", "rank_age65", "weight_raw", "weight"]},
            "disclaimer": DISCLAIMER}


def methodology() -> dict:
    return {
        "units": {"distance": "metres", "time": "minutes", "speed": "km/h", "demand": "persons (estimated)"},
        "speed_model": {"posted_speed_used_if_within_kph": list(POSTED_SPEED_RANGE), "class_default_kph": CLASS_SPEED_KPH,
                        "walk_speed_m_per_min": WALK_SPEED_M_PER_MIN},
        "defaults": {"demand": DemandParams().model_dump(), "weights": EquityWeights().model_dump(),
                     "access": AccessParams().model_dump(mode="json"), "resources": Resources().model_dump(),
                     "solver": SolverSettings().model_dump()},
        "scenario_presets": list_presets(),
        "optimization_model": {
            "objective": "min sum_o w_o u_o + a_walk*sum(c_oh/W)x_oh + a_walk*sum(c_os/W)g_os + a_drive*sum(t_hs/T)f_hs "
                         "+ 1e-3*sum(r_hs/T)n_hs + a_hub*sum y_h",
            "constraints": [
                "demand conservation: sum_h x_oh + sum_s g_os + u_o = D_o",
                "activation link: x_oh <= D_o y_h",
                "hub capacity: sum_o x_oh <= K y_h",
                "hub flow balance: sum_o x_oh = sum_s f_hs",
                "vehicle capacity: f_hs <= Q n_hs",
                "fleet time: sum r_hs n_hs <= V T, with r_hs = t_hs + t_sh + dwell <= T",
                "per-leg trips: n_hs <= V floor(T / r_hs)",
                "shelter capacity: sum_h f_hs + sum_o g_os <= C_s",
                "hub budget: sum_h y_h <= P",
            ],
            "approximation": "Fleet-time capacity model, not a vehicle routing/scheduling solution.",
            "docs": ["docs/OPTIMIZATION_MODEL.md", "docs/SCENARIO_ENGINE.md", "docs/ACCESSIBILITY_METHODS.md"],
        },
        "equity_weights": "w_t = 1 + beta_pov*rank(pct_below_poverty) + beta_dis*rank(pct_with_disability) "
                          "[+ beta_65*rank(pct_65_plus), default 0]; normalised to demand-weighted mean 1. "
                          "Rates only adjust priority; they never add persons to demand.",
        "disclaimer": DISCLAIMER,
    }


# ------------------------------------------------------------------- demo
DEMO = {
    "title": "Southwest Houston: severe hypothetical bayou flooding, 12 pickup hubs, 15 buses",
    "request": CompareRequest(disrupted_scenario="severe").model_dump(mode="json"),
    "story": [
        "1. Baseline access: walk-only access to assumed shelters (community centres) on the intact network.",
        "2. Hypothetical severe flood rules close roads in and near FEMA 1%/0.2% zones (Fort Bend side only; Harris "
        "side has no FEMA data and is reported as unknown).",
        "3. Accessibility deterioration per tract: lost walk access and lost drive routes.",
        "4. Communities most affected: ranked by demand-weighted access loss.",
        "5. Limited resources: 12 hubs, 15 vehicles x 40 seats, 8-hour horizon, 400 persons per shelter.",
        "6. Optimised recommendations: activated hubs, hub-to-shelter legs and trips.",
        "7. Modelled improvement versus the disrupted no-intervention case and versus equal weighting.",
    ],
}


def demo(repo: DataRepository, region_id: str) -> dict:
    result = compare(repo, region_id, CompareRequest(**DEMO["request"]))
    return {"title": DEMO["title"], "story": DEMO["story"], "request": DEMO["request"],
            "reproduce": f"POST /api/v1/regions/{region_id}/compare with the 'request' body", "result": result}
