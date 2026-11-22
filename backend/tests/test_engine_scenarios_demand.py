"""Engines B, C, D on the synthetic fixture (3x3 grid, known flood box)."""

import numpy as np
import pandas as pd
import pytest

from app.engine.accessibility import analyze, scenario_state
from app.engine.context import get_engine
from app.engine.demand import priority_weights, sensitivity, tract_demand
from app.engine.params import AccessParams, DemandParams, EquityWeights, ScenarioSpec
from app.engine.scenarios import PRESETS, UnknownEdgeError, _uniform, compute_closures, scenario_id

R = "houston-sw-pilot"


@pytest.fixture
def eng(repo, synthetic_region):
    return get_engine(repo, R)


# ------------------------------------------------------------------ Engine B
def test_demand_formula_from_household_size_cells(eng):
    d = tract_demand(eng.vehicle_access, eng.demographics, DemandParams()).set_index("geoid")
    # tract 1: 10x1 + 10x2 + 10x3 + 10x4.5 = 105 persons; 50% participation
    assert d.loc["48201990100", "persons_zero_vehicle_est"] == pytest.approx(105)
    assert d.loc["48201990100", "demand_est"] == pytest.approx(52.5)
    assert d.loc["48201990200", "demand_est"] == pytest.approx(0.5 * (50 + 100 + 150 + 225))
    assert d.loc["48157990300", "demand_est"] == 0  # observed zero, not missing
    d2 = tract_demand(eng.vehicle_access, eng.demographics,
                      DemandParams(participation_rate=1.0, persons_in_4plus_households=5)).set_index("geoid")
    assert d2.loc["48201990100", "demand_est"] == pytest.approx(110)


def test_missing_size_cells_fallback_and_null(eng):
    va = eng.vehicle_access.copy().set_index("geoid")
    va.loc["48201990100", "hh_no_vehicle_1p"] = pd.NA  # tract 1: size cells incomplete
    va.loc["48201990200", ["hh_no_vehicle", "hh_no_vehicle_1p"]] = pd.NA  # tract 2: nothing usable
    va = va.reset_index()
    d = tract_demand(va, eng.demographics, DemandParams()).set_index("geoid")
    # fallback: 40 households x mean household size (1000 / 400 = 2.5) x 0.5
    assert d.loc["48201990100", "demand_method"] == "total_x_mean_household_size"
    assert d.loc["48201990100", "demand_est"] == pytest.approx(40 * 2.5 * 0.5)
    assert d.loc["48201990200", "demand_method"] == "unavailable"
    assert pd.isna(d.loc["48201990200", "demand_est"])  # null, never 0


def test_vulnerability_indicators_do_not_add_demand(eng):
    """Overlap avoidance: changing poverty/disability/age rates changes priority, never persons."""
    demo = eng.demographics.copy()
    base = tract_demand(eng.vehicle_access, demo, DemandParams())["demand_est"]
    demo["pct_below_poverty"] = 99.0
    demo["pct_65_plus"] = 99.0
    demo["pct_with_disability"] = 99.0
    np.testing.assert_allclose(tract_demand(eng.vehicle_access, demo, DemandParams())["demand_est"], base)


def test_priority_weights_transparent_and_normalised(eng):
    d = tract_demand(eng.vehicle_access, eng.demographics, DemandParams())
    w = priority_weights(eng.demographics, d, EquityWeights(beta_poverty=1.0, beta_disability=0.0))
    # Demand-weighted mean of weights is exactly 1.
    assert np.average(w["weight"], weights=d["demand_est"]) == pytest.approx(1.0, abs=1e-5)
    wi = w.set_index("geoid")
    # Tract 4 has missing poverty -> neutral rank 0.5, flagged.
    assert wi.loc["48157990400", "rank_poverty"] == 0.5
    assert any("pct_below_poverty_missing" in f for f in wi.loc["48157990400", "weight_flags"])
    # Raw weight = 1 + beta * rank, rank in [0, 1].
    assert wi["weight_raw"].between(1, 2).all()
    eq = priority_weights(eng.demographics, d, EquityWeights(mode="equal"))
    assert (eq["weight"] == 1).all()


def test_sensitivity_monotonic(eng):
    rows = sensitivity(eng.vehicle_access, eng.demographics, [0.25, 0.5, 1.0], [4.0, 5.0])
    totals = {(r["participation_rate"], r["persons_in_4plus_households"]): r["total_demand"] for r in rows}
    assert totals[(0.25, 4.0)] < totals[(0.5, 4.0)] < totals[(1.0, 4.0)] < totals[(1.0, 5.0)]


def test_origin_shares_sum_to_one(eng):
    o = eng.origins(500).table
    assert o.groupby("geoid")["share"].sum().round(9).eq(1).all()
    assert set(o["geoid"]) == set(eng.tracts["geoid"])


# ------------------------------------------------------------------ Engine C
def test_severe_closes_exactly_the_exposed_segments(eng):
    cr = compute_closures(eng, PRESETS["severe"])
    closed_ids = set(eng.net.edge_ids[cr.closed])
    # fz-1 (1% zone) covers node 1000: the 1000-1001 and 1000-1010 streets, both directions.
    assert closed_ids == {"1000-1001-0", "1001-1000-0", "1000-1010-0", "1010-1000-0"}
    assert cr.by_rule["fema_1pct"] == 2
    assert compute_closures(eng, PRESETS["baseline"]).closed.sum() == 0


def test_closures_deterministic_and_seed_dependent(eng):
    spec = ScenarioSpec(one_pct_closure_prob=0.5, min_exposed_m=1)
    a, b = compute_closures(eng, spec).closed, compute_closures(eng, spec).closed
    np.testing.assert_array_equal(a, b)
    keys = np.array([f"k{i}" for i in range(2000)])
    u1, u2 = _uniform(1, "r", keys), _uniform(2, "r", keys)
    np.testing.assert_array_equal(u1, _uniform(1, "r", keys))
    assert (u1 != u2).mean() > 0.99 and 0.45 < (u1 < 0.5).mean() < 0.55
    sid = scenario_id(R, eng.stamp, spec)
    assert sid == scenario_id(R, eng.stamp, spec) and sid != scenario_id(R, eng.stamp, PRESETS["severe"])


def test_unknown_coverage_never_closed_under_no_inference(eng):
    eng.exposure["len_in_coverage_m"] = 0.0  # pretend no FEMA coverage anywhere
    eng.__dict__.pop("_segment_table", None)
    spec = ScenarioSpec(overbank_buffer_m=500, overbank_closure_prob=1.0)
    cr = compute_closures(eng, spec)
    assert cr.closed.sum() == 0 and cr.unknown_segments > 0
    stress = ScenarioSpec(unknown_coverage_policy="stress_sample", unknown_closure_prob=1.0)
    assert compute_closures(eng, stress).closed.sum() == eng.net.n_edges


def test_unknown_probability_requires_stress_policy():
    with pytest.raises(ValueError):
        ScenarioSpec(unknown_closure_prob=0.3)


def test_custom_closures_both_directions_and_validation(eng):
    cr = compute_closures(eng, ScenarioSpec(custom_closed_edge_ids=["1011-1012-0"]))
    assert set(eng.net.edge_ids[cr.closed]) == {"1011-1012-0", "1012-1011-0"}
    with pytest.raises(UnknownEdgeError):
        compute_closures(eng, ScenarioSpec(custom_closed_edge_ids=["9-9-9"]))


# ------------------------------------------------------------------ Engine D
def test_accessibility_deteriorates_under_disruption(eng):
    access = AccessParams(walk_max_m=1500)
    base = scenario_state(eng, PRESETS["baseline"], access, 500)
    sev = scenario_state(eng, PRESETS["severe"], access, 500)
    # Node 1000 is cut off; origins snapped to it lose every drive route.
    lost = np.isfinite(base.drive_origin_nearest_shelter) & ~np.isfinite(sev.drive_origin_nearest_shelter)
    assert lost.any()
    finite = np.isfinite(sev.drive_origin_nearest_shelter)
    assert (sev.drive_origin_nearest_shelter[finite] >= base.drive_origin_nearest_shelter[finite] - 1e-9).all()
    table, summary, _, _ = analyze(eng, PRESETS["severe"], access, DemandParams())
    t1 = table.set_index("geoid").loc["48201990100"]
    assert t1["newly_no_drive_route_share"] > 0
    assert summary["demand_newly_without_drive_route"] > 0
    # Unreachable stays null, never 0.
    assert table["drive_min_to_nearest_shelter"].isna().sum() + (table["drive_min_to_nearest_shelter"] > 0).sum() == len(table)


def test_baseline_network_not_mutated_by_scenarios(eng):
    before = eng.net.time_min.copy()
    scenario_state(eng, PRESETS["severe"], AccessParams(), 500)
    np.testing.assert_array_equal(before, eng.net.time_min)


def test_shelter_flood_status_is_unknown_outside_coverage(eng):
    dest = eng.destinations(AccessParams())
    assert dest.shelters["flood_status"].tolist() == ["unknown_no_fema_data"]
    assert len(dest.hubs) == 2 and "syn-4" not in set(dest.hubs["facility_id"])
