"""Phase 2 analysis endpoints (/api/v1/regions/{region_id}/...).

Handlers are plain ``def`` functions, so FastAPI executes them in its worker
threadpool; CPU-heavy work never runs on the event loop. A semaphore in the
service layer bounds concurrent jobs, and solver calls carry time limits.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Path, Query

from app.api.deps import Repo
from app.engine import service
from app.engine.params import (
    AccessibilityRequest,
    CompareRequest,
    DemandParams,
    EquityWeights,
    OptimizeRequest,
    ScenarioEvaluateRequest,
)
from app.regions import get_region
from app.schemas.analysis import (
    AccessibilityResult,
    ComparisonResult,
    DemoResult,
    OptimizationResult,
    ScenarioEvaluation,
    ScenarioPreset,
)

router = APIRouter(prefix="/regions/{region_id}", tags=["analysis"])
RegionId = Annotated[str, Path(pattern=r"^[a-z0-9][a-z0-9-]*$")]


@router.get("/scenarios", response_model=list[ScenarioPreset], summary="Scenario presets")
def scenarios(region_id: RegionId) -> list[dict]:
    get_region(region_id)
    return service.list_presets()


@router.post("/scenarios/evaluate", response_model=ScenarioEvaluation, summary="Evaluate a disruption scenario")
def evaluate(region_id: RegionId, body: ScenarioEvaluateRequest, repo: Repo) -> dict:
    return service.evaluate_scenario(repo, region_id, body)


@router.get("/scenarios/{scenario_id}/closures", summary="Simulated closed road segments (GeoJSON)")
def closures(
    region_id: RegionId,
    scenario_id: Annotated[str, Path(pattern=r"^scn_[0-9a-f]{16}$")],
    repo: Repo,
    limit: Annotated[int, Query(ge=1, le=5000)] = 1000,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> dict:
    return service.closures_geojson(repo, region_id, scenario_id, limit, offset)


@router.post("/accessibility/analyze", response_model=AccessibilityResult,
             summary="Tract accessibility, baseline vs scenario (GeoJSON)")
def accessibility(region_id: RegionId, body: AccessibilityRequest, repo: Repo) -> dict:
    return service.analyze_accessibility(repo, region_id, body)


@router.post("/demand", summary="Evacuation-assistance demand estimates, weights and sensitivity")
def demand(region_id: RegionId, repo: Repo, params: DemandParams | None = None,
           weights: EquityWeights | None = None) -> dict:
    return service.demand_estimates(repo, region_id, params or DemandParams(), weights or EquityWeights())


@router.post("/optimize", response_model=OptimizationResult, summary="Equity-aware hub + transport optimisation (MILP)")
def optimize(region_id: RegionId, body: OptimizeRequest, repo: Repo) -> dict:
    return service.optimize(repo, region_id, body)


@router.post("/compare", response_model=ComparisonResult, summary="Counterfactual before/after comparison")
def compare(region_id: RegionId, body: CompareRequest, repo: Repo) -> dict:
    return service.compare(repo, region_id, body)


@router.get("/methodology", summary="Model formulation, defaults and assumptions")
def methodology(region_id: RegionId) -> dict[str, Any]:
    get_region(region_id)
    return service.methodology()


@router.get("/demo", response_model=DemoResult, summary="Reproducible Phase 3 demonstration scenario")
def demo(region_id: RegionId, repo: Repo) -> dict:
    return service.demo(repo, region_id)
