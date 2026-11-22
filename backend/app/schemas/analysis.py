"""Response models for Phase 2 analysis endpoints.

Core blocks are fully typed; free-form diagnostic blocks (timings, model
size) are dicts. ``extra="allow"`` keeps responses forward compatible.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict


class _Open(BaseModel):
    model_config = ConfigDict(extra="allow")


class ScenarioPreset(_Open):
    name: str
    description: str
    spec: dict[str, Any]


class ClosureStats(_Open):
    closed_directed_edges: int
    closed_segments: int
    closed_length_km: float
    closed_segments_by_rule: dict[str, int]
    unknown_coverage_segments: int
    unknown_coverage_length_km: float
    unknown_coverage_policy: str
    note: str


class ScenarioEvaluation(_Open):
    scenario_id: str
    region_id: str
    spec: dict[str, Any]
    description: str
    closures: ClosureStats
    network: dict[str, dict[str, int]]
    access_change: dict[str, Any]
    speed_model: dict[str, Any]
    timings_s: dict[str, float]
    provenance: dict[str, Any]
    disclaimer: str
    cache: str


class AccessibilityResult(_Open):
    type: str = "FeatureCollection"
    scenario_id: str
    region_id: str
    spec: dict[str, Any]
    summary: dict[str, Any]
    features: list[dict[str, Any]]
    units: dict[str, str]
    method_notes: list[str]
    disclaimer: str
    cache: str


class OptimizationTotals(_Open):
    demand_est: float
    served: float
    served_via_hubs: float
    served_by_direct_walk_to_shelter: float
    unmet: float
    coverage: float | None
    weighted_unmet_run_weights: float
    weighted_unmet_equity_weights: float
    weighted_coverage_equity_weights: float | None
    active_hubs: int
    vehicle_trips: int
    vehicle_minutes_used: float | None
    vehicle_minutes_available: float
    fleet_utilization: float | None
    mean_walk_m_served_via_hub: float | None
    mean_bus_drive_min: float | None
    mean_seat_occupancy: float | None


class SolverReport(_Open):
    status: str
    message: str
    objective: float | None
    mip_gap: float | None
    dual_bound: float | None
    solve_seconds: float
    build_seconds: float
    model_size: dict[str, Any]
    screening: dict[str, Any]
    engine: str
    settings: dict[str, Any]
    optimality_claim: str


class ConstraintCheck(_Open):
    feasible: bool
    tolerance: float | None = None
    max_violation: dict[str, float] = {}
    max_trip_integrality_gap: float | None = None
    vehicle_minutes_used: float | None = None
    vehicle_minutes_available: float | None = None
    active_hubs: int | None = None


class HubLeg(_Open):
    shelter_id: str
    shelter_name: str | None
    persons: float
    trips: int
    drive_min: float
    round_trip_min: float


class ActivatedHub(_Open):
    hub_id: str
    facility_id: str
    name: str | None
    category: str
    lon: float
    lat: float
    flood_status: str
    persons_assigned: float
    capacity_utilization: float | None
    mean_walk_m: float | None
    origins_served: int
    legs: list[HubLeg]


class OptimizationResult(_Open):
    region_id: str
    scenario_id: str
    scenario: dict[str, Any]
    totals: OptimizationTotals
    binding_constraints: dict[str, Any]
    distribution_by_priority_tercile: dict[str, dict[str, Any]]
    hubs: list[ActivatedHub]
    shelters: list[dict[str, Any]]
    tracts: list[dict[str, Any]]
    solver: SolverReport
    constraint_check: ConstraintCheck
    weights_used: dict[str, Any]
    assumptions: dict[str, Any]
    disclaimer: str
    cache: str


class ComparisonCase(_Open):
    case: str
    label: str
    scenario_id: str
    totals: OptimizationTotals
    distribution_by_priority_tercile: dict[str, dict[str, Any]]
    binding_constraints: dict[str, Any]
    solver_status: str
    mip_gap: float | None
    constraint_check_feasible: bool
    active_hub_ids: list[str]


class ComparisonResult(_Open):
    region_id: str
    scenario_id: str
    disrupted_scenario: dict[str, Any]
    cases: list[ComparisonCase]
    deltas: dict[str, dict[str, float | None]]
    findings: list[str]
    accessibility_change: dict[str, Any]
    most_affected_tracts: list[dict[str, Any]]
    identical_inputs: dict[str, Any]
    disclaimer: str
    cache: str


class DemoResult(_Open):
    title: str
    story: list[str]
    request: dict[str, Any]
    reproduce: str
    result: ComparisonResult
