"""Request/parameter models for the Phase 2 engines.

Every numeric assumption is explicit, bounded and documented here so API
requests stay small and auditable. Values marked HYPOTHETICAL are planning
assumptions, not observations.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.facilities import FacilityCategory


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ScenarioSpec(_Strict):
    """Hypothetical road-disruption rules. Exposure comes from FEMA
    regulatory zones; closure probabilities are HYPOTHETICAL."""

    name: str = Field(default="custom", max_length=80)
    seed: int = Field(default=2017, ge=0, le=2**31 - 1, description="Deterministic sampling seed")
    one_pct_closure_prob: float = Field(default=0.0, ge=0, le=1,
                                        description="P(close) for segments with >= min_exposed_m inside a 1%-annual-chance zone")
    point_two_pct_closure_prob: float = Field(default=0.0, ge=0, le=1,
                                              description="P(close) for segments inside a 0.2%-annual-chance zone")
    min_exposed_m: float = Field(default=10.0, ge=0, le=1000)
    overbank_buffer_m: float = Field(default=0.0, ge=0, le=500,
                                     description="Segments within this distance of a 1% zone are 'overbank' candidates")
    overbank_closure_prob: float = Field(default=0.0, ge=0, le=1)
    unknown_coverage_policy: Literal["no_inference", "stress_sample"] = Field(
        default="no_inference",
        description="no_inference: roads without FEMA data are never closed by flood rules and are reported as "
        "unknown; stress_sample: close uncovered segments with unknown_closure_prob (sensitivity test only)",
    )
    unknown_closure_prob: float = Field(default=0.0, ge=0, le=1)
    custom_closed_edge_ids: list[str] = Field(default_factory=list, max_length=5000)

    @model_validator(mode="after")
    def _check(self) -> "ScenarioSpec":
        if self.unknown_coverage_policy == "no_inference" and self.unknown_closure_prob > 0:
            raise ValueError("unknown_closure_prob requires unknown_coverage_policy='stress_sample'")
        return self


class DemandParams(_Strict):
    """Engine B assumptions."""

    participation_rate: float = Field(
        default=0.5, ge=0, le=1,
        description="HYPOTHETICAL share of persons in zero-vehicle households who request assisted evacuation",
    )
    persons_in_4plus_households: float = Field(
        default=4.5, ge=4, le=8, description="Assumed mean size of 4-or-more-person households (ACS cell is open-ended)"
    )
    origin_cell_m: float = Field(default=500, ge=200, le=2000, description="Sub-tract origin grid size")


class EquityWeights(_Strict):
    """Priority weight w_t = 1 + sum_k beta_k * rank_k(t), normalised to a
    demand-weighted mean of 1. rank_k is the within-region percentile rank
    (0-1) of a tract-level RATE; rates modify priority, they never add people."""

    mode: Literal["equity", "equal"] = "equity"
    beta_poverty: float = Field(default=0.5, ge=0, le=5, description="Weight on pct_below_poverty rank")
    beta_disability: float = Field(default=0.5, ge=0, le=5, description="Weight on pct_with_disability rank")
    beta_age65: float = Field(
        default=0.0, ge=0, le=5,
        description="Weight on pct_65_plus rank; 0 by default because it overlaps the disability indicator",
    )


class AccessParams(_Strict):
    walk_max_m: float = Field(default=800, ge=100, le=2000, description="Max walking network distance to a hub/shelter")
    drive_thresholds_min: list[float] = Field(default=[10, 20, 30], min_length=1, max_length=5)
    shelter_categories: list[FacilityCategory] = Field(
        default=[FacilityCategory.community_centre],
        description="HYPOTHETICAL: facility categories assumed usable as shelter destinations",
    )
    exclude_shelters_in_1pct_zone: bool = True

    @model_validator(mode="after")
    def _thresholds(self) -> "AccessParams":
        if any(t <= 0 or t > 180 for t in self.drive_thresholds_min):
            raise ValueError("drive thresholds must be in (0, 180] minutes")
        self.drive_thresholds_min = sorted(set(self.drive_thresholds_min))
        return self


class Resources(_Strict):
    """HYPOTHETICAL resource budget for the intervention."""

    max_active_hubs: int = Field(default=12, ge=0, le=100)
    vehicles: int = Field(default=15, ge=0, le=500)
    vehicle_capacity: int = Field(default=40, ge=1, le=120, description="Persons per trip")
    horizon_min: float = Field(default=480, gt=0, le=2880, description="Planning horizon (minutes)")
    dwell_min: float = Field(default=10, ge=0, le=120, description="Loading + unloading time per trip")
    hub_capacity: float = Field(default=600, ge=0, le=100000, description="Persons a hub can process in the horizon")
    shelter_capacity: float = Field(default=400, ge=0, le=100000, description="Persons per assumed shelter")
    shelters_per_hub: int = Field(default=4, ge=1, le=20, description="Nearest reachable shelters considered per hub")


class SolverSettings(_Strict):
    time_limit_s: float = Field(default=30, gt=0, le=120)
    mip_rel_gap: float = Field(default=0.005, ge=0, le=0.2)
    integer_trips: bool = Field(default=True, description="Integer vehicle trips (True) or fluid relaxation (False)")
    walk_cost_weight: float = Field(default=0.01, ge=0, le=0.1, description="Objective penalty per person per walk_max_m")
    drive_cost_weight: float = Field(default=0.01, ge=0, le=0.1, description="Penalty per person per horizon of bus time")
    hub_activation_cost: float = Field(default=0.1, ge=0, le=10, description="Penalty per activated hub (persons-equivalent)")


class OptimizeRequest(_Strict):
    scenario: ScenarioSpec | str = Field(default="severe", description="Preset name or explicit spec")
    demand: DemandParams = DemandParams()
    weights: EquityWeights = EquityWeights()
    access: AccessParams = AccessParams()
    resources: Resources = Resources()
    solver: SolverSettings = SolverSettings()
    include_geometry: bool = True


class AccessibilityRequest(_Strict):
    scenario: ScenarioSpec | str = "severe"
    demand: DemandParams = DemandParams()
    access: AccessParams = AccessParams()
    include_geometry: bool = True
    simplify_m: float | None = Field(default=20, gt=0, le=500)


class CompareRequest(_Strict):
    disrupted_scenario: ScenarioSpec | str = "severe"
    demand: DemandParams = DemandParams()
    weights: EquityWeights = EquityWeights()
    access: AccessParams = AccessParams()
    resources: Resources = Resources()
    solver: SolverSettings = SolverSettings()
    include_robustness_case: bool = Field(
        default=True, description="Also evaluate the baseline-optimised hub plan under disruption"
    )


class ScenarioEvaluateRequest(_Strict):
    scenario: ScenarioSpec | str = "moderate"
    access: AccessParams = AccessParams()
    include_closures_geojson: bool = Field(default=False, description="Inline closed segments (capped at 2000)")
