"""End-to-end Phase 2 checks on the REAL Houston pilot data (skipped if absent)."""

import time

import numpy as np
import pytest

from app.core.config import get_settings
from app.engine import service
from app.engine.context import get_engine
from app.engine.params import AccessParams, CompareRequest, DemandParams, EquityWeights, Resources, SolverSettings
from app.engine.scenarios import PRESETS, compute_closures
from app.services.repository import DataRepository

settings = get_settings()
MANIFEST = settings.processed_dir / "houston-sw-pilot" / "manifest.json"
pytestmark = pytest.mark.skipif(
    not (settings.processed_dir / "houston-sw-pilot" / "edge_flood_exposure.parquet").exists(),
    reason="real processed data (incl. Phase 2 derived datasets) not generated",
)
R = "houston-sw-pilot"


@pytest.fixture(scope="module")
def repo():
    return DataRepository(settings)


def test_real_routing_and_closures(repo):
    eng = get_engine(repo, R)
    assert eng.net.n_edges == 199_542 and eng.net.n_nodes == 88_404
    a = compute_closures(eng, PRESETS["severe"]).closed
    b = compute_closures(eng, PRESETS["severe"]).closed
    np.testing.assert_array_equal(a, b)
    assert 0 < a.sum() < 0.1 * eng.net.n_edges
    # Under no_inference, no segment entirely outside FEMA coverage is closed by the overbank rule.
    exp = eng.exposure
    outside = exp["len_in_coverage_m"].to_numpy() <= 0.0
    in_zone = (exp["len_in_1pct_m"].to_numpy() > 0) | (exp["len_in_0_2pct_m"].to_numpy() > 0)
    assert not (a & outside & ~in_zone).any()


def test_real_optimization_end_to_end(repo):
    eng = get_engine(repo, R)
    t0 = time.perf_counter()
    out = service.run_optimization(eng, PRESETS["severe"], DemandParams(), EquityWeights(), AccessParams(),
                                   Resources(), SolverSettings())
    elapsed = time.perf_counter() - t0
    t = out["totals"]
    assert out["constraint_check"]["feasible"]
    assert all(v <= out["constraint_check"]["tolerance"] for v in out["constraint_check"]["max_violation"].values())
    assert out["solver"]["status"] in ("optimal", "optimal_within_gap")
    assert 0 < t["served"] < t["demand_est"] and t["active_hubs"] <= Resources().max_active_hubs
    assert t["served"] + t["unmet"] == pytest.approx(t["demand_est"], rel=1e-6, abs=0.5)
    assert elapsed < 90


def test_real_compare_intervention_not_worse(repo):
    res = service.compare(repo, R, CompareRequest(include_robustness_case=False))
    cases = {c["case"]: c["totals"] for c in res["cases"]}
    assert cases["disrupted_equity_optimized"]["served"] >= cases["disrupted_no_intervention"]["served"]
    assert cases["baseline_no_intervention"]["served"] >= cases["disrupted_no_intervention"]["served"] - 1e-6
    assert res["accessibility_change"]["total_demand_est"] > 10_000
