"""Engine D: evacuation accessibility under a scenario.

Per scenario, the engine computes (all with SciPy compiled Dijkstra, reusing
searches rather than one search per origin-destination pair):

* walk distances origin -> hubs and origin -> shelters: one *bounded*
  Dijkstra per hub/shelter on the undirected walk-proxy graph (cut off at
  ``WALK_SEARCH_LIMIT_M``), read at origin nodes;
* drive minutes hub -> shelter and shelter -> hub: one full Dijkstra per
  shelter on the transposed / forward directed graph;
* drive minutes origin -> nearest shelter: a single multi-source Dijkstra
  (``min_only``) on the transposed graph;
* counts of shelters reachable within each drive threshold.

Unreachable = ``inf`` internally and ``null`` in JSON, never 0.
"""

from __future__ import annotations

import threading
import time
from collections import OrderedDict
from dataclasses import dataclass, field

import numpy as np
import pandas as pd
import scipy.sparse as sp

from app.engine.context import Destinations, RegionEngine
from app.engine.demand import Origins, tract_demand
from app.engine.network import WALK_SPEED_M_PER_MIN, component_stats, nearest_target
from app.engine.params import AccessParams, DemandParams, ScenarioSpec
from app.engine.scenarios import ClosureResult, compute_closures, scenario_id

WALK_SEARCH_LIMIT_M = 2000.0
CHUNK = 64


def _columns(matrix: sp.csr_matrix, targets: np.ndarray, cols: np.ndarray, limit: float) -> np.ndarray:
    """cost[target, col] from every col-node TO each target, chunked to bound memory."""
    out = np.full((len(targets), len(cols)), np.inf)
    T = matrix.T.tocsr()
    from scipy.sparse.csgraph import dijkstra

    for i in range(0, len(targets), CHUNK):
        block = dijkstra(T, directed=True, indices=targets[i:i + CHUNK], limit=limit)
        out[i:i + CHUNK] = block[:, cols]
    return out


def _from_sources(matrix: sp.csr_matrix, sources: np.ndarray, cols: np.ndarray) -> np.ndarray:
    from scipy.sparse.csgraph import dijkstra

    out = np.full((len(sources), len(cols)), np.inf)
    for i in range(0, len(sources), CHUNK):
        block = dijkstra(matrix, directed=True, indices=sources[i:i + CHUNK])
        out[i:i + CHUNK] = block[:, cols]
    return out


@dataclass
class ScenarioState:
    scenario_id: str
    spec: ScenarioSpec
    closures: ClosureResult
    origins: Origins
    dest: Destinations
    walk_origin_hub: np.ndarray  # (O, H) metres, inf beyond WALK_SEARCH_LIMIT_M
    walk_origin_shelter: np.ndarray  # (O, S)
    drive_hub_shelter: np.ndarray  # (H, S) minutes
    drive_shelter_hub: np.ndarray  # (S, H) minutes
    drive_origin_nearest_shelter: np.ndarray  # (O,) minutes
    drive_origin_shelter_counts: dict[float, np.ndarray]  # threshold -> (O,) counts
    components: dict[str, int]
    timings_s: dict[str, float] = field(default_factory=dict)


_cache: "OrderedDict[str, ScenarioState]" = OrderedDict()
_cache_lock = threading.Lock()
CACHE_SIZE = 12


def _access_key(access: AccessParams, cell_m: float) -> str:
    return f"{sorted(c.value for c in access.shelter_categories)}|{access.exclude_shelters_in_1pct_zone}|" \
           f"{access.drive_thresholds_min}|{cell_m}"


def scenario_state(eng: RegionEngine, spec: ScenarioSpec, access: AccessParams, cell_m: float) -> ScenarioState:
    sid = scenario_id(eng.region.region_id, eng.stamp, spec)
    key = f"{sid}|{_access_key(access, cell_m)}"
    with _cache_lock:
        if key in _cache:
            _cache.move_to_end(key)
            return _cache[key]
    timings: dict[str, float] = {}
    t = time.perf_counter()
    closures = compute_closures(eng, spec)
    timings["closures"] = time.perf_counter() - t
    t = time.perf_counter()
    drive = eng.net.drive_matrix(closures.closed)
    walk = eng.net.walk_matrix(closures.closed)
    timings["matrices"] = time.perf_counter() - t
    origins = eng.origins(cell_m)
    dest = eng.destinations(access)
    o_walk = origins.table["walk_node"].to_numpy()
    o_drive = origins.table["drive_node"].to_numpy()
    h_walk, s_walk = dest.hubs["walk_node"].to_numpy(), dest.shelters["walk_node"].to_numpy()
    h_drive, s_drive = dest.hubs["node"].to_numpy(), dest.shelters["node"].to_numpy()
    t = time.perf_counter()
    w_oh = _columns(walk, h_walk, o_walk, WALK_SEARCH_LIMIT_M).T
    w_os = _columns(walk, s_walk, o_walk, WALK_SEARCH_LIMIT_M).T
    timings["walk_searches"] = time.perf_counter() - t
    t = time.perf_counter()
    d_hs = _columns(drive, s_drive, h_drive, np.inf).T  # hub -> shelter
    d_sh = _from_sources(drive, s_drive, h_drive)  # shelter -> hub
    nearest, _ = nearest_target(drive, s_drive)
    near_o = nearest[o_drive]
    tmax = max(access.drive_thresholds_min)
    to_shel = _columns(drive, s_drive, o_drive, tmax)  # (S, O)
    counts = {thr: (to_shel <= thr).sum(axis=0) for thr in access.drive_thresholds_min}
    timings["drive_searches"] = time.perf_counter() - t
    t = time.perf_counter()
    comps = component_stats(drive)
    timings["components"] = time.perf_counter() - t
    state = ScenarioState(sid, spec, closures, origins, dest, w_oh, w_os, d_hs, d_sh, near_o, counts, comps,
                          {k: round(v, 3) for k, v in timings.items()})
    with _cache_lock:
        _cache[key] = state
        while len(_cache) > CACHE_SIZE:
            _cache.popitem(last=False)
    return state


def clear_cache() -> None:
    with _cache_lock:
        _cache.clear()


# ---------------------------------------------------------------- tract table
def _wmean(values: np.ndarray, weights: np.ndarray) -> float | None:
    ok = np.isfinite(values) & (weights > 0)
    if not ok.any():
        return None
    return float(np.average(values[ok], weights=weights[ok]))


def tract_accessibility(eng: RegionEngine, st: ScenarioState, access: AccessParams, demand: pd.DataFrame) -> pd.DataFrame:
    """Demand-share-weighted tract metrics. Within a tract, origins are
    weighted by their share of tract demand (residential street length)."""
    o = st.origins.table
    walk_max = access.walk_max_m
    near_hub = st.walk_origin_hub.min(axis=1) if st.walk_origin_hub.shape[1] else np.full(len(o), np.inf)
    near_shel_walk = st.walk_origin_shelter.min(axis=1) if st.walk_origin_shelter.shape[1] else np.full(len(o), np.inf)
    n_hubs_walk = (st.walk_origin_hub <= walk_max).sum(axis=1)
    rows = []
    for geoid, idx in o.groupby("geoid").indices.items():
        share = o["share"].to_numpy()[idx]
        dt = st.drive_origin_nearest_shelter[idx]
        nh = near_hub[idx]
        row = {
            "geoid": geoid,
            "origins": len(idx),
            "drive_min_to_nearest_shelter": _wmean(dt, share),
            "share_demand_no_drive_route_to_shelter": float(share[~np.isfinite(dt)].sum()),
            "walk_m_to_nearest_hub": _wmean(np.where(nh <= WALK_SEARCH_LIMIT_M, nh, np.inf), share),
            "share_demand_within_walk_of_hub": float(share[nh <= walk_max].sum()),
            "share_demand_within_walk_of_shelter": float(share[near_shel_walk[idx] <= walk_max].sum()),
            "hubs_within_walk": float(np.average(n_hubs_walk[idx], weights=share)) if share.sum() else 0.0,
            "disconnected_from_shelters": bool(not np.isfinite(dt).any()),
        }
        for thr, cnt in st.drive_origin_shelter_counts.items():
            row[f"shelters_within_{int(thr) if float(thr).is_integer() else thr}_min"] = float(
                np.average(cnt[idx], weights=share)) if share.sum() else 0.0
        rows.append(row)
    df = pd.DataFrame(rows)
    df = df.merge(demand[["geoid", "demand_est"]], on="geoid", how="left")
    df["walk_min_to_nearest_hub"] = df["walk_m_to_nearest_hub"] / WALK_SPEED_M_PER_MIN
    return df


def compare_tracts(base: pd.DataFrame, scn: pd.DataFrame) -> pd.DataFrame:
    """Baseline vs scenario deterioration per tract (positive = worse)."""
    m = base.merge(scn, on="geoid", suffixes=("_baseline", "_scenario"))
    out = pd.DataFrame({"geoid": m["geoid"]})
    out["delta_drive_min_to_nearest_shelter"] = m["drive_min_to_nearest_shelter_scenario"] - m[
        "drive_min_to_nearest_shelter_baseline"]
    out["lost_share_within_walk_of_hub"] = m["share_demand_within_walk_of_hub_baseline"] - m[
        "share_demand_within_walk_of_hub_scenario"]
    out["newly_no_drive_route_share"] = m["share_demand_no_drive_route_to_shelter_scenario"] - m[
        "share_demand_no_drive_route_to_shelter_baseline"]
    d = m["demand_est_scenario"].fillna(0)
    out["demand_weighted_walk_access_loss"] = (d * out["lost_share_within_walk_of_hub"]).round(2)
    out["demand_newly_without_drive_route"] = (d * out["newly_no_drive_route_share"]).round(2)
    return out


def analyze(eng: RegionEngine, spec: ScenarioSpec, access: AccessParams, demand_params: DemandParams):  # type: ignore[no-untyped-def]
    """Return (tract table with baseline+scenario+deltas, summary dict, states)."""
    from app.engine.scenarios import PRESETS

    demand = tract_demand(eng.vehicle_access, eng.demographics, demand_params)
    base_state = scenario_state(eng, PRESETS["baseline"], access, demand_params.origin_cell_m)
    st = scenario_state(eng, spec, access, demand_params.origin_cell_m)
    base = tract_accessibility(eng, base_state, access, demand)
    scn = tract_accessibility(eng, st, access, demand)
    deltas = compare_tracts(base, scn)
    table = scn.merge(deltas, on="geoid").merge(
        base[["geoid", "drive_min_to_nearest_shelter", "share_demand_within_walk_of_hub",
              "share_demand_no_drive_route_to_shelter"]].rename(columns=lambda c: c if c == "geoid" else f"{c}_baseline"),
        on="geoid")
    d = table["demand_est"].fillna(0)
    total = float(d.sum())

    def dw(col: str, frame: pd.DataFrame) -> float | None:
        ok = frame[col].notna()
        return round(float((frame.loc[ok, col] * d[ok]).sum() / d[ok].sum()), 4) if d[ok].sum() else None

    summary = {
        "total_demand_est": round(total, 1),
        "baseline": {
            "demand_share_within_walk_of_hub": dw("share_demand_within_walk_of_hub", base),
            "demand_share_within_walk_of_shelter": dw("share_demand_within_walk_of_shelter", base),
            "demand_share_no_drive_route_to_shelter": dw("share_demand_no_drive_route_to_shelter", base),
            "mean_drive_min_to_nearest_shelter": dw("drive_min_to_nearest_shelter", base),
        },
        "scenario": {
            "demand_share_within_walk_of_hub": dw("share_demand_within_walk_of_hub", scn),
            "demand_share_within_walk_of_shelter": dw("share_demand_within_walk_of_shelter", scn),
            "demand_share_no_drive_route_to_shelter": dw("share_demand_no_drive_route_to_shelter", scn),
            "mean_drive_min_to_nearest_shelter": dw("drive_min_to_nearest_shelter", scn),
        },
        "tracts_disconnected_from_shelters": int(scn["disconnected_from_shelters"].sum()),
        "tracts_with_walk_access_loss": int((deltas["lost_share_within_walk_of_hub"] > 1e-9).sum()),
        "tracts_with_longer_drive": int((deltas["delta_drive_min_to_nearest_shelter"] > 0.05).sum()),
        "demand_weighted_walk_access_loss": round(float(deltas["demand_weighted_walk_access_loss"].sum()), 1),
        "demand_newly_without_drive_route": round(float(deltas["demand_newly_without_drive_route"].sum()), 1),
    }
    return table, summary, base_state, st
