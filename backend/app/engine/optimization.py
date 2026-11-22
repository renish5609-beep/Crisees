"""Engine E: equity-aware pickup-hub activation and transport allocation (MILP).

Sets: origins o (sub-tract cells with demand), candidate hubs h, assumed
shelters s, hub-shelter legs (h,s) restricted to each hub's k nearest
reachable shelters whose round trip fits the horizon.

Decision variables
    y_h  in {0,1}   activate hub h
    x_oh >= 0       persons walking from origin o to hub h        (walk <= W)
    g_os >= 0       persons walking directly from o to shelter s  (walk <= W)
    f_hs >= 0       persons carried from hub h to shelter s
    n_hs in Z>=0    vehicle trips on leg (h,s)                     (or >=0 real if relaxed)
    u_o  >= 0       unmet demand at origin o

Objective (minimise)
    sum_o w_o u_o
  + a_walk  * sum (c_oh / W) x_oh + a_walk * sum (c_os / W) g_os
  + a_drive * sum (t_hs / T) f_hs + 1e-3 * sum (r_hs / T) n_hs
  + a_hub   * sum y_h
with w_o the tract priority weight (mean 1 over demand) or 1 for the equal-
weight baseline. Penalty coefficients are small (default <= 0.02 per person),
so serving one more person always dominates; they only break ties toward
shorter walks/drives and fewer hubs.

Constraints
  (1) demand conservation  sum_h x_oh + sum_s g_os + u_o = D_o
  (2) activation link       x_oh <= D_o y_h
  (3) hub capacity          sum_o x_oh <= K_h y_h
  (4) hub flow balance      sum_o x_oh = sum_s f_hs      (reaching a hub is not evacuation)
  (5) vehicle capacity      f_hs <= Q n_hs
  (6) fleet time budget     sum_hs r_hs n_hs <= V T,     r_hs = t_hs + t_sh + dwell <= T
  (7) per-leg trip bound    n_hs <= V floor(T / r_hs)
  (8) shelter capacity      sum_h f_hs + sum_o g_os <= C_s
  (9) hub budget            sum_h y_h <= P

(6) is a capacity (fluid fleet-time) approximation: it guarantees enough
vehicle-minutes for all trips but does not schedule individual vehicles,
deadhead from a depot, or sequence trips. It is not a vehicle-routing solution.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass

import numpy as np
import pandas as pd
import scipy.sparse as sp
from scipy.optimize import Bounds, LinearConstraint, milp

from app.engine.accessibility import ScenarioState
from app.engine.network import WALK_SPEED_M_PER_MIN
from app.engine.params import AccessParams, Resources, SolverSettings

TOL = 1e-6


@dataclass
class OptimizationInputs:
    demand_o: np.ndarray  # persons per origin
    weight_o: np.ndarray  # priority weight per origin
    geoid_o: np.ndarray
    walk_oh: np.ndarray  # (O, H) metres
    walk_os: np.ndarray  # (O, S)
    drive_hs: np.ndarray  # (H, S) minutes
    drive_sh: np.ndarray  # (S, H)
    hub_ids: np.ndarray
    shelter_ids: np.ndarray


def inputs_from_state(st: ScenarioState, demand: pd.DataFrame, weights: pd.DataFrame) -> OptimizationInputs:
    o = st.origins.table
    d = demand.set_index("geoid")["demand_est"]
    w = weights.set_index("geoid")["weight"]
    tract_d = d.reindex(o["geoid"]).to_numpy(float)
    tract_d = np.where(np.isfinite(tract_d), tract_d, 0.0)  # null demand tracts excluded (flagged upstream)
    return OptimizationInputs(
        demand_o=tract_d * o["share"].to_numpy(),
        weight_o=w.reindex(o["geoid"]).fillna(1.0).to_numpy(float),
        geoid_o=o["geoid"].to_numpy(),
        walk_oh=st.walk_origin_hub, walk_os=st.walk_origin_shelter,
        drive_hs=st.drive_hub_shelter, drive_sh=st.drive_shelter_hub,
        hub_ids=st.dest.hubs["hub_id"].to_numpy(), shelter_ids=st.dest.shelters["facility_id"].to_numpy(),
    )


@dataclass
class Solution:
    status: str
    message: str
    objective: float | None
    mip_gap: float | None
    dual_bound: float | None
    solve_seconds: float
    build_seconds: float
    model_size: dict
    y: dict  # hub index -> value
    x: pd.DataFrame  # o, h, persons, walk_m
    g: pd.DataFrame  # o, s, persons, walk_m
    f: pd.DataFrame  # h, s, persons, trips, drive_min, round_trip_min
    u: np.ndarray
    screening: dict
    constraint_check: dict


STATUS = {0: "optimal", 1: "time_limit", 2: "infeasible", 3: "unbounded", 4: "solver_error"}


def solve(inp: OptimizationInputs, access: AccessParams, res: Resources, solver: SolverSettings,
          fixed_hubs: list[str] | None = None) -> Solution:
    t_build = time.perf_counter()
    W, T, Q, V = access.walk_max_m, res.horizon_min, res.vehicle_capacity, res.vehicles
    D = inp.demand_o
    act = np.flatnonzero(D > TOL)
    O_all = len(D)
    H, S = len(inp.hub_ids), len(inp.shelter_ids)

    # ---- candidate legs: k nearest reachable shelters per hub, round trip within horizon
    legs = []
    if S and H and V > 0 and Q > 0:
        r_all = inp.drive_hs + inp.drive_sh.T + res.dwell_min
        for h in range(H):
            ok = np.flatnonzero(np.isfinite(r_all[h]) & (r_all[h] <= T))
            ok = ok[np.argsort(inp.drive_hs[h, ok], kind="stable")][: res.shelters_per_hub]
            legs.extend((h, s, inp.drive_hs[h, s], r_all[h, s]) for s in ok)
    legs_arr = np.array(legs, dtype=float).reshape(-1, 4)
    hubs_with_leg = set(legs_arr[:, 0].astype(int)) if len(legs_arr) else set()

    # ---- walking pairs
    oh = [(o, h, inp.walk_oh[o, h]) for o in act for h in np.flatnonzero(inp.walk_oh[o] <= W) if h in hubs_with_leg]
    os_ = [(o, s, inp.walk_os[o, s]) for o in act for s in np.flatnonzero(inp.walk_os[o] <= W)]
    hubs_with_demand = sorted({h for _, h, _ in oh})
    allowed = set(range(H)) if fixed_hubs is None else set(np.flatnonzero(np.isin(inp.hub_ids, fixed_hubs)))
    cand = [h for h in hubs_with_demand if (res.max_active_hubs > 0 or fixed_hubs is not None)]
    screening = {
        "hubs_total": H,
        "hubs_with_feasible_shelter_leg": len(hubs_with_leg),
        "hubs_with_walkable_demand": len(hubs_with_demand),
        "hubs_in_model": len(cand),
        "walk_max_m": W,
        "rule": "A hub is modelled only if it can serve someone: >=1 origin with demand within walk_max_m AND "
                ">=1 shelter leg whose round trip fits the horizon. No other pruning, so no community loses its "
                "only feasible option.",
    }
    hidx = {h: i for i, h in enumerate(cand)}
    oh = [p for p in oh if p[1] in hidx]
    leg_rows = [i for i in range(len(legs_arr)) if int(legs_arr[i, 0]) in hidx]
    legs_arr = legs_arr[leg_rows] if len(legs_arr) else legs_arr
    nY, nX, nG, nF, nU = len(cand), len(oh), len(os_), len(legs_arr), len(act)
    nN = nF
    off_y, off_x = 0, nY
    off_g = off_x + nX
    off_f = off_g + nG
    off_n = off_f + nF
    off_u = off_n + nN
    nv = off_u + nU
    uidx = {o: i for i, o in enumerate(act)}

    c = np.zeros(nv)
    c[off_u:] = inp.weight_o[act]
    for i, (_, _, d) in enumerate(oh):
        c[off_x + i] = solver.walk_cost_weight * d / W
    for i, (_, _, d) in enumerate(os_):
        c[off_g + i] = solver.walk_cost_weight * d / W
    if nF:
        c[off_f:off_f + nF] = solver.drive_cost_weight * legs_arr[:, 2] / T
        c[off_n:off_n + nN] = 1e-3 * legs_arr[:, 3] / T
    c[off_y:off_y + nY] = solver.hub_activation_cost

    rows, cols, vals, lb, ub = [], [], [], [], []
    r = 0

    def add(entries: list[tuple[int, float]], lo: float, hi: float) -> None:
        nonlocal r
        for j, v in entries:
            rows.append(r)
            cols.append(j)
            vals.append(v)
        lb.append(lo)
        ub.append(hi)
        r += 1

    by_o_x: dict[int, list[int]] = {}
    by_h_x: dict[int, list[int]] = {}
    for i, (o, h, _) in enumerate(oh):
        by_o_x.setdefault(o, []).append(i)
        by_h_x.setdefault(h, []).append(i)
    by_o_g: dict[int, list[int]] = {}
    by_s_g: dict[int, list[int]] = {}
    for i, (o, s, _) in enumerate(os_):
        by_o_g.setdefault(o, []).append(i)
        by_s_g.setdefault(s, []).append(i)
    by_h_f: dict[int, list[int]] = {}
    by_s_f: dict[int, list[int]] = {}
    for i in range(nF):
        by_h_f.setdefault(int(legs_arr[i, 0]), []).append(i)
        by_s_f.setdefault(int(legs_arr[i, 1]), []).append(i)

    for o in act:  # (1)
        e = [(off_x + i, 1.0) for i in by_o_x.get(o, [])] + [(off_g + i, 1.0) for i in by_o_g.get(o, [])]
        e.append((off_u + uidx[o], 1.0))
        add(e, D[o], D[o])
    for i, (o, h, _) in enumerate(oh):  # (2)
        add([(off_x + i, 1.0), (off_y + hidx[h], -D[o])], -np.inf, 0.0)
    for h in cand:  # (3), (4)
        xs = by_h_x.get(h, [])
        add([(off_x + i, 1.0) for i in xs] + [(off_y + hidx[h], -res.hub_capacity)], -np.inf, 0.0)
        add([(off_x + i, 1.0) for i in xs] + [(off_f + i, -1.0) for i in by_h_f.get(h, [])], 0.0, 0.0)
    for i in range(nF):  # (5)
        add([(off_f + i, 1.0), (off_n + i, -float(Q))], -np.inf, 0.0)
    if nF:  # (6)
        add([(off_n + i, float(legs_arr[i, 3])) for i in range(nF)], -np.inf, V * T)
    for s in range(S):  # (8)
        e = [(off_f + i, 1.0) for i in by_s_f.get(s, [])] + [(off_g + i, 1.0) for i in by_s_g.get(s, [])]
        if e:
            add(e, -np.inf, res.shelter_capacity)
    if nY:  # (9)
        add([(off_y + i, 1.0) for i in range(nY)], -np.inf,
            float(res.max_active_hubs if fixed_hubs is None else nY))

    lo_b = np.zeros(nv)
    hi_b = np.full(nv, np.inf)
    hi_b[off_y:off_y + nY] = 1.0
    if fixed_hubs is not None:
        for h, i in hidx.items():
            fixed = h in allowed
            lo_b[off_y + i] = hi_b[off_y + i] = 1.0 if fixed else 0.0
    if nN:  # (7)
        hi_b[off_n:off_n + nN] = V * np.floor(T / legs_arr[:, 3])
    integrality = np.zeros(nv)
    integrality[off_y:off_y + nY] = 1
    if solver.integer_trips:
        integrality[off_n:off_n + nN] = 1
    A = sp.csr_matrix((vals, (rows, cols)), shape=(r, nv))
    build_s = time.perf_counter() - t_build
    size = {"variables": nv, "binary": nY, "integer_trips": nN if solver.integer_trips else 0, "constraints": r,
            "nonzeros": int(A.nnz), "origins_with_demand": nU, "walk_pairs_hub": nX, "walk_pairs_shelter": nG,
            "hub_shelter_legs": nF}

    t_solve = time.perf_counter()
    if nv == 0 or nU == 0:
        res_x, status, msg, obj, gap, bound = np.zeros(nv), "optimal", "Trivial model: no demand.", 0.0, 0.0, 0.0
    else:
        out = milp(c, constraints=LinearConstraint(A, lb, ub), integrality=integrality, bounds=Bounds(lo_b, hi_b),
                   options={"time_limit": solver.time_limit_s, "mip_rel_gap": solver.mip_rel_gap, "presolve": True})
        status = STATUS.get(out.status, "solver_error")
        msg = str(out.message)
        res_x = out.x
        obj = float(out.fun) if out.x is not None else None
        is_mip = bool(integrality.any())
        gap_raw = getattr(out, "mip_gap", None) if out.x is not None else None
        bound_raw = getattr(out, "mip_dual_bound", None) if out.x is not None else None
        gap = float(gap_raw) if gap_raw is not None and np.isfinite(gap_raw) else (0.0 if not is_mip and out.status == 0 else None)
        bound = float(bound_raw) if bound_raw is not None and np.isfinite(bound_raw) else (obj if not is_mip else None)
        if status == "time_limit":
            status = "time_limit_feasible" if out.x is not None else "time_limit_no_solution"
        elif status == "optimal" and gap is not None and gap > 1e-9:
            status = "optimal_within_gap"
    solve_s = time.perf_counter() - t_solve

    if res_x is None:
        empty = pd.DataFrame()
        return Solution(status, msg, None, None, None, round(solve_s, 3), round(build_s, 3), size, {}, empty, empty,
                        empty, np.zeros(O_all), screening, {"feasible": False})

    xv = np.clip(res_x, 0, None)
    y = {cand[i]: float(round(xv[off_y + i])) for i in range(nY)}
    xdf = pd.DataFrame([(o, h, xv[off_x + i], d) for i, (o, h, d) in enumerate(oh)], columns=["o", "h", "persons", "walk_m"])
    gdf = pd.DataFrame([(o, s, xv[off_g + i], d) for i, (o, s, d) in enumerate(os_)], columns=["o", "s", "persons", "walk_m"])
    fdf = pd.DataFrame({"h": legs_arr[:, 0].astype(int) if nF else [], "s": legs_arr[:, 1].astype(int) if nF else [],
                        "persons": xv[off_f:off_f + nF], "trips": xv[off_n:off_n + nN],
                        "drive_min": legs_arr[:, 2] if nF else [], "round_trip_min": legs_arr[:, 3] if nF else []})
    u = np.zeros(O_all)
    u[act] = xv[off_u:]
    check = verify(inp, access, res, y, xdf, gdf, fdf, u, fixed_hubs)
    return Solution(status, msg, obj, gap, bound, round(solve_s, 3), round(build_s, 3), size, y,
                    xdf[xdf.persons > TOL].reset_index(drop=True), gdf[gdf.persons > TOL].reset_index(drop=True),
                    fdf[(fdf.persons > TOL) | (fdf.trips > TOL)].reset_index(drop=True), u, screening, check)


def verify(inp: OptimizationInputs, access: AccessParams, res: Resources, y: dict, x: pd.DataFrame, g: pd.DataFrame,
           f: pd.DataFrame, u: np.ndarray, fixed_hubs: list[str] | None) -> dict:
    """Recompute every constraint from the solution, independent of the solver.
    Returns the maximum violation per constraint family (persons/minutes)."""
    D = inp.demand_o
    O = len(D)
    served_x = np.bincount(x["o"].astype(int), weights=x["persons"], minlength=O) if len(x) else np.zeros(O)
    served_g = np.bincount(g["o"].astype(int), weights=g["persons"], minlength=O) if len(g) else np.zeros(O)
    viol: dict[str, float] = {}
    viol["demand_conservation"] = float(np.abs(served_x + served_g + u - D).max()) if O else 0.0
    hub_in = x.groupby("h")["persons"].sum() if len(x) else pd.Series(dtype=float)
    hub_out = f.groupby("h")["persons"].sum() if len(f) else pd.Series(dtype=float)
    idx = hub_in.index.union(hub_out.index)
    viol["hub_flow_balance"] = float((hub_in.reindex(idx, fill_value=0) - hub_out.reindex(idx, fill_value=0)).abs().max()) if len(idx) else 0.0
    viol["hub_capacity"] = float(max([0.0] + [v - res.hub_capacity * y.get(h, 0) for h, v in hub_in.items()]))
    viol["inactive_hub_use"] = float(max([0.0] + [v for h, v in hub_in.items() if y.get(h, 0) < 0.5]))
    viol["walk_limit"] = float(max([0.0] + list(x["walk_m"] - access.walk_max_m) + list(g["walk_m"] - access.walk_max_m)))
    viol["vehicle_capacity"] = float(max([0.0] + list(f["persons"] - res.vehicle_capacity * f["trips"]))) if len(f) else 0.0
    used = float((f["trips"] * f["round_trip_min"]).sum()) if len(f) else 0.0
    viol["fleet_time"] = max(0.0, used - res.vehicles * res.horizon_min)
    viol["leg_round_trip_within_horizon"] = float(max([0.0] + list(f["round_trip_min"] - res.horizon_min))) if len(f) else 0.0
    shel = pd.concat([f.groupby("s")["persons"].sum() if len(f) else pd.Series(dtype=float),
                      g.groupby("s")["persons"].sum() if len(g) else pd.Series(dtype=float)]).groupby(level=0).sum()
    viol["shelter_capacity"] = float(max([0.0] + list(shel - res.shelter_capacity)))
    active = sum(1 for v in y.values() if v > 0.5)
    viol["hub_budget"] = 0.0 if fixed_hubs is not None else float(max(0, active - res.max_active_hubs))
    viol["nonnegativity"] = float(max(0.0, -min([0.0, *u, *x.get("persons", []), *f.get("persons", [])])))
    trips_integral = float(max([0.0] + [abs(t - round(t)) for t in f["trips"]])) if len(f) else 0.0
    tol = 1e-4 * max(1.0, float(D.sum()))
    return {
        "feasible": all(v <= tol for v in viol.values()),
        "tolerance": tol,
        "max_violation": {k: round(v, 9) for k, v in viol.items()},
        "max_trip_integrality_gap": round(trips_integral, 9),
        "vehicle_minutes_used": round(used, 1),
        "vehicle_minutes_available": res.vehicles * res.horizon_min,
        "active_hubs": active,
        "walk_speed_m_per_min": WALK_SPEED_M_PER_MIN,
    }


def ceil_trips_needed(persons: float, q: int) -> int:
    return math.ceil(persons / q - 1e-9)
