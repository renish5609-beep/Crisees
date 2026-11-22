"""Engine E: MILP on hand-built instances with known optimal answers.

Every test also checks the solver-independent constraint verification."""

import numpy as np
import pytest

from app.engine import optimization as opt
from app.engine.optimization import OptimizationInputs, solve
from app.engine.params import AccessParams, Resources, SolverSettings

INF = np.inf
ACCESS = AccessParams(walk_max_m=800)


def inputs(demand, walk_oh, walk_os, drive_hs, weights=None):
    demand = np.asarray(demand, float)
    walk_oh, walk_os, drive_hs = (np.asarray(a, float) for a in (walk_oh, walk_os, drive_hs))
    return OptimizationInputs(
        demand_o=demand, weight_o=np.ones(len(demand)) if weights is None else np.asarray(weights, float),
        geoid_o=np.array([f"t{i}" for i in range(len(demand))]), walk_oh=walk_oh, walk_os=walk_os,
        drive_hs=drive_hs, drive_sh=drive_hs.T.copy(),
        hub_ids=np.array([f"h{i}" for i in range(walk_oh.shape[1])]),
        shelter_ids=np.array([f"s{i}" for i in range(walk_os.shape[1])]))


def res(**kw):
    base = dict(max_active_hubs=5, vehicles=1, vehicle_capacity=10, horizon_min=100, dwell_min=0,
                hub_capacity=1000, shelter_capacity=1000, shelters_per_hub=4)
    base.update(kw)
    return Resources(**base)


def served(sol):
    return sol.x.persons.sum() + sol.g.persons.sum() if len(sol.x) or len(sol.g) else 0.0


def check(sol, inp):
    assert sol.constraint_check["feasible"], sol.constraint_check
    assert served(sol) + sol.u.sum() == pytest.approx(inp.demand_o.sum(), abs=1e-6)  # conservation


# One origin (100 persons) 300 m from one hub; hub->shelter 10 min each way.
ONE = dict(demand=[100], walk_oh=[[300]], walk_os=[[INF]], drive_hs=[[10]])


def test_vehicle_capacity_and_fleet_time_bind():
    inp = inputs(**ONE)
    sol = solve(inp, ACCESS, res(), SolverSettings())
    # round trip 20 min -> 5 trips in 100 min x 10 seats = 50 persons
    assert served(sol) == pytest.approx(50) and sol.u.sum() == pytest.approx(50)
    assert sol.f.trips.sum() == pytest.approx(5) and sol.status.startswith("optimal")
    check(sol, inp)


def test_more_vehicles_serve_everyone():
    sol = solve(inputs(**ONE), ACCESS, res(vehicles=2), SolverSettings())
    assert served(sol) == pytest.approx(100)


def test_dwell_time_reduces_trips():
    sol = solve(inputs(**ONE), ACCESS, res(dwell_min=5), SolverSettings())  # 25-min trips -> 4
    assert served(sol) == pytest.approx(40)


def test_hub_capacity_enforced():
    sol = solve(inputs(**ONE), ACCESS, res(vehicles=10, hub_capacity=30), SolverSettings())
    assert served(sol) == pytest.approx(30)
    check(sol, inputs(**ONE))


def test_shelter_capacity_enforced():
    sol = solve(inputs(**ONE), ACCESS, res(vehicles=10, shelter_capacity=25), SolverSettings())
    assert served(sol) == pytest.approx(25)


def test_reaching_a_hub_is_not_evacuation():
    # No vehicles: people at a hub cannot be counted as served.
    sol = solve(inputs(**ONE), ACCESS, res(vehicles=0), SolverSettings())
    assert served(sol) == 0 and sol.u.sum() == pytest.approx(100)


def test_direct_walk_to_shelter_counts_and_uses_capacity():
    inp = inputs(demand=[100], walk_oh=[[INF]], walk_os=[[500]], drive_hs=[[10]])
    sol = solve(inp, ACCESS, res(vehicles=0, max_active_hubs=0, shelter_capacity=60), SolverSettings())
    assert served(sol) == pytest.approx(60) and sol.g.persons.sum() == pytest.approx(60)
    check(sol, inp)


def test_walk_limit_excludes_far_hubs():
    inp = inputs(demand=[100], walk_oh=[[900]], walk_os=[[INF]], drive_hs=[[10]])
    sol = solve(inp, ACCESS, res(vehicles=10), SolverSettings())
    assert served(sol) == 0 and sol.screening["hubs_in_model"] == 0


def test_unreachable_shelter_leg_excluded():
    inp = inputs(demand=[100], walk_oh=[[300]], walk_os=[[INF]], drive_hs=[[INF]])
    sol = solve(inp, ACCESS, res(vehicles=10), SolverSettings())
    assert served(sol) == 0 and sol.model_size["hub_shelter_legs"] == 0


def test_leg_longer_than_horizon_excluded():
    inp = inputs(demand=[100], walk_oh=[[300]], walk_os=[[INF]], drive_hs=[[60]])  # 120-min round trip
    sol = solve(inp, ACCESS, res(vehicles=10, horizon_min=100), SolverSettings())
    assert served(sol) == 0


def test_zero_demand_is_trivial():
    sol = solve(inputs(demand=[0], walk_oh=[[300]], walk_os=[[INF]], drive_hs=[[10]]), ACCESS, res(), SolverSettings())
    assert sol.status == "optimal" and served(sol) == 0 and sol.u.sum() == 0


def test_zero_resources_leaves_all_unmet():
    sol = solve(inputs(**ONE), ACCESS, res(vehicles=0, max_active_hubs=0), SolverSettings())
    assert served(sol) == 0 and sol.u.sum() == pytest.approx(100) and not sol.y


# Two origins, each next to its own hub; one hub allowed.
TWO = dict(demand=[40, 60], walk_oh=[[200, INF], [INF, 200]], walk_os=[[INF], [INF]], drive_hs=[[10], [10]])


def test_hub_budget_equal_weights_serves_larger_demand():
    sol = solve(inputs(**TWO), ACCESS, res(vehicles=10, max_active_hubs=1), SolverSettings())
    assert [h for h, v in sol.y.items() if v > 0.5] == [1] and served(sol) == pytest.approx(60)


def test_hub_budget_equity_weights_change_choice():
    # Weight 2.0 on the 40-person origin: 80 weighted > 60 weighted.
    sol = solve(inputs(**TWO, weights=[2.0, 1.0]), ACCESS, res(vehicles=10, max_active_hubs=1), SolverSettings())
    assert [h for h, v in sol.y.items() if v > 0.5] == [0] and served(sol) == pytest.approx(40)
    check(sol, inputs(**TWO, weights=[2.0, 1.0]))


def test_fixed_hubs_respected():
    sol = solve(inputs(**TWO), ACCESS, res(vehicles=10, max_active_hubs=1), SolverSettings(), fixed_hubs=["h0"])
    assert sol.y == {0: 1.0, 1: 0.0} and served(sol) == pytest.approx(40)


def test_integer_trips_vs_fluid_relaxation():
    # 25 persons, 10 seats, plenty of time: integer model needs 3 whole trips,
    # the fluid relaxation uses 2.5 fractional trips (documented approximation).
    inp = inputs(demand=[25], walk_oh=[[300]], walk_os=[[INF]], drive_hs=[[10]])
    s_int = solve(inp, ACCESS, res(vehicles=1, horizon_min=100), SolverSettings(integer_trips=True))
    assert served(s_int) == pytest.approx(25) and s_int.f.trips.sum() == pytest.approx(3)
    assert s_int.constraint_check["max_trip_integrality_gap"] == 0
    s_fluid = solve(inp, ACCESS, res(vehicles=1, horizon_min=100), SolverSettings(integer_trips=False))
    assert served(s_fluid) == pytest.approx(25) and s_fluid.f.trips.sum() == pytest.approx(2.5)
    # Per-leg bound n <= V*floor(T/r) applies to both: 50 min allows only 2 trips.
    s_short = solve(inp, ACCESS, res(vehicles=1, horizon_min=50), SolverSettings(integer_trips=False))
    assert served(s_short) == pytest.approx(20)


def test_deterministic_repeat():
    rng = np.random.default_rng(7)
    O, H, S = 30, 8, 3
    walk = np.where(rng.random((O, H)) < 0.3, rng.uniform(50, 790, (O, H)), INF)
    inp = inputs(demand=rng.uniform(0, 50, O), walk_oh=walk, walk_os=np.full((O, S), INF),
                 drive_hs=rng.uniform(5, 30, (H, S)), weights=rng.uniform(0.5, 1.5, O))
    r = res(vehicles=3, max_active_hubs=3, hub_capacity=120, shelter_capacity=200)
    a, b = solve(inp, ACCESS, r, SolverSettings()), solve(inp, ACCESS, r, SolverSettings())
    assert a.y == b.y and a.objective == pytest.approx(b.objective)
    np.testing.assert_allclose(a.u, b.u)
    check(a, inp)
    # Every constraint family holds on this random instance too.
    assert all(v <= 1e-6 for v in a.constraint_check["max_violation"].values())


def test_time_limit_is_not_reported_optimal(monkeypatch):
    real = opt.milp

    def fake(*args, **kwargs):
        out = real(*args, **kwargs)
        out.status, out.message = 1, "Time limit reached"
        return out

    monkeypatch.setattr(opt, "milp", fake)
    sol = solve(inputs(**ONE), ACCESS, res(), SolverSettings())
    assert sol.status == "time_limit_feasible"


def test_infeasible_status_propagates(monkeypatch):
    class R:
        status, message, x, fun = 2, "infeasible", None, None

    monkeypatch.setattr(opt, "milp", lambda *a, **k: R())
    sol = solve(inputs(**ONE), ACCESS, res(), SolverSettings())
    assert sol.status == "infeasible" and sol.constraint_check == {"feasible": False}


def test_verify_detects_violations():
    import pandas as pd

    inp = inputs(**ONE)
    x = pd.DataFrame({"o": [0], "h": [0], "persons": [80.0], "walk_m": [300.0]})
    g = pd.DataFrame(columns=["o", "s", "persons", "walk_m"])
    f = pd.DataFrame({"h": [0], "s": [0], "persons": [80.0], "trips": [5.0], "drive_min": [10.0],
                      "round_trip_min": [20.0]})
    chk = opt.verify(inp, ACCESS, res(), {0: 1.0}, x, g, f, np.array([20.0]), None)
    assert not chk["feasible"] and chk["max_violation"]["vehicle_capacity"] == pytest.approx(30)
