"""Phase 2 API contract tests on the synthetic fixture (numbers checked, not just 200s)."""

import pytest

R = "/api/v1/regions/houston-sw-pilot"
SMALL = {"resources": {"max_active_hubs": 2, "vehicles": 2, "vehicle_capacity": 20, "horizon_min": 240,
                       "hub_capacity": 500, "shelter_capacity": 500},
         "access": {"walk_max_m": 1500}}


def test_scenario_presets(client):
    body = client.get(f"{R}/scenarios").json()
    assert [p["name"] for p in body] == ["baseline", "moderate", "severe"]
    assert body[2]["spec"]["one_pct_closure_prob"] == 1.0


def test_evaluate_and_closures(client):
    r = client.post(f"{R}/scenarios/evaluate", json={"scenario": "severe"})
    assert r.status_code == 200
    body = r.json()
    assert body["closures"]["closed_directed_edges"] == 4 and body["closures"]["closed_segments"] == 2
    assert body["scenario_id"].startswith("scn_") and body["cache"] == "miss"
    assert client.post(f"{R}/scenarios/evaluate", json={"scenario": "severe"}).json()["cache"] == "hit"
    geo = client.get(f"{R}/scenarios/{body['scenario_id']}/closures").json()
    assert geo["page"]["total"] == 2 and geo["evidence_type"] == "simulated"
    assert all(f["properties"]["both_directions_closed"] for f in geo["features"])
    assert client.get(f"{R}/scenarios/scn_0000000000000000/closures").status_code == 404


def test_evaluate_validation_errors(client):
    assert client.post(f"{R}/scenarios/evaluate", json={"scenario": "bogus"}).status_code == 400
    assert client.post(f"{R}/scenarios/evaluate", json={"scenario": {"seed": -1}}).status_code == 422
    assert client.post(f"{R}/scenarios/evaluate", json={"scenario": "severe", "extra": 1}).status_code == 422
    r = client.post(f"{R}/scenarios/evaluate", json={"scenario": {"custom_closed_edge_ids": ["x"]}})
    assert r.status_code == 400 and r.json()["error"]["code"] == "unknown_edge_ids"


def test_accessibility_geojson(client):
    body = client.post(f"{R}/accessibility/analyze", json={"scenario": "severe", **{"access": SMALL["access"]}}).json()
    assert body["type"] == "FeatureCollection" and len(body["features"]) == 4
    props = {f["id"]: f["properties"] for f in body["features"]}
    assert props["48201990100"]["newly_no_drive_route_share"] > 0
    assert body["features"][0]["geometry"]["type"] == "Polygon"
    assert body["summary"]["demand_newly_without_drive_route"] > 0


def test_optimize_satisfies_constraints(client):
    r = client.post(f"{R}/optimize", json={"scenario": "baseline", **SMALL})
    assert r.status_code == 200, r.text
    b = r.json()
    t = b["totals"]
    assert b["constraint_check"]["feasible"] is True
    assert t["served"] + t["unmet"] == pytest.approx(t["demand_est"], abs=0.2)
    assert t["served"] == pytest.approx(t["served_via_hubs"] + t["served_by_direct_walk_to_shelter"], abs=0.2)
    assert t["active_hubs"] <= 2 and b["solver"]["status"] in ("optimal", "optimal_within_gap")
    assert t["served"] > 0
    for h in b["hubs"]:
        assert h["persons_assigned"] <= 500 + 1e-6
        assert sum(l["persons"] for l in h["legs"]) == pytest.approx(h["persons_assigned"], abs=0.2)
        for leg in h["legs"]:
            assert leg["persons"] <= leg["trips"] * 20 + 1e-6
    assert sum(s["persons"] for s in b["shelters"]) == pytest.approx(t["served"], abs=0.2)
    assert b["tracts_geojson"]["features"] and b["hubs_geojson"]["type"] == "FeatureCollection"


def test_optimize_zero_resources(client):
    body = {**SMALL, "resources": {**SMALL["resources"], "max_active_hubs": 0, "vehicles": 0}}
    t = client.post(f"{R}/optimize", json={"scenario": "baseline", **body}).json()["totals"]
    assert t["served_via_hubs"] == 0 and t["active_hubs"] == 0 and t["vehicle_trips"] == 0


def test_optimize_request_bounds(client):
    for bad in [{"resources": {"vehicles": -1}}, {"resources": {"max_active_hubs": 1000}},
                {"access": {"walk_max_m": 50}}, {"solver": {"time_limit_s": 999}}, {"demand": {"participation_rate": 2}}]:
        assert client.post(f"{R}/optimize", json=bad).status_code == 422, bad


def test_optimize_infeasible_returns_422(client, monkeypatch):
    from app.engine import optimization

    class Res:
        status, message, x, fun = 2, "infeasible", None, None

    monkeypatch.setattr(optimization, "milp", lambda *a, **k: Res())
    r = client.post(f"{R}/optimize", json={"scenario": "baseline", **SMALL})
    assert r.status_code == 422 and r.json()["error"]["code"] == "optimization_failed"


def test_compare_counterfactuals_consistent(client):
    r = client.post(f"{R}/compare", json={"disrupted_scenario": "severe", **SMALL})
    assert r.status_code == 200, r.text
    b = r.json()
    cases = {c["case"]: c for c in b["cases"]}
    assert set(cases) == {"baseline_no_intervention", "disrupted_no_intervention", "disrupted_equity_optimized",
                          "disrupted_equal_weight_optimized", "baseline_plan_under_disruption"}
    for c in cases.values():
        assert c["constraint_check_feasible"]
    for name in ("baseline_no_intervention", "disrupted_no_intervention"):
        assert cases[name]["totals"]["active_hubs"] == 0 and cases[name]["totals"]["vehicle_trips"] == 0
    # Same demand in every case (identical inputs).
    assert len({c["totals"]["demand_est"] for c in cases.values()}) == 1
    # Deltas are exact differences of the case totals.
    d = b["deltas"]["intervention_effect (disrupted_equity_optimized - disrupted_no_intervention)"]
    assert d["served"] == pytest.approx(cases["disrupted_equity_optimized"]["totals"]["served"]
                                        - cases["disrupted_no_intervention"]["totals"]["served"], abs=1e-3)
    # Optimising with hubs can only add options to the no-intervention model.
    assert cases["disrupted_equity_optimized"]["totals"]["served"] >= cases["disrupted_no_intervention"]["totals"]["served"] - 1e-6
    # Equity optimisation minimises equity-weighted unmet demand, so it cannot be worse than equal weights on it
    # (up to the MIP gap).
    gap = 0.005 * cases["disrupted_equal_weight_optimized"]["totals"]["demand_est"]
    assert cases["disrupted_equity_optimized"]["totals"]["weighted_unmet_equity_weights"] <= \
        cases["disrupted_equal_weight_optimized"]["totals"]["weighted_unmet_equity_weights"] + gap + 1
    assert b["findings"] and b["identical_inputs"]["resources"]["vehicles"] == 2


def test_demand_methodology_and_demo(client):
    d = client.post(f"{R}/demand", json={"params": {"participation_rate": 1.0}}).json()
    assert d["total_demand_est"] == pytest.approx(105 + 525 + 0 + 30 * 1 + 0)  # tract 4: 30 one-person hh
    assert len(d["sensitivity"]) == 12
    m = client.get(f"{R}/methodology").json()
    assert "hub flow balance: sum_o x_oh = sum_s f_hs" in m["optimization_model"]["constraints"]
    demo = client.get(f"{R}/demo")
    assert demo.status_code == 200 and demo.json()["result"]["cases"]


def test_analysis_endpoints_503_without_data(empty_client):
    for path, body in [("optimize", {}), ("compare", {}), ("accessibility/analyze", {}), ("scenarios/evaluate", {})]:
        r = empty_client.post(f"{R}/{path}", json=body)
        assert r.status_code == 503 and r.json()["error"]["code"] == "dataset_not_available", path
