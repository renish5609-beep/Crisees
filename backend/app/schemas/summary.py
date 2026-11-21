from __future__ import annotations

from pydantic import BaseModel, Field

from app.schemas.common import Provenance


class PopulationSummary(BaseModel):
    tract_count: int
    tracts_with_demographics: int
    total_population: int | None
    households_total: int | None
    households_no_vehicle: int | None
    pct_households_no_vehicle: float | None
    population_below_poverty: int | None
    pct_below_poverty: float | None
    population_65_plus: int | None
    pct_65_plus: float | None
    population_with_disability: int | None
    pct_with_disability: float | None
    tracts_with_missing_values: int = Field(description="Tracts missing any core percentage indicator")
    note: str = "Sums of ACS tract estimates; aggregate MOEs are not computed in Phase 1."


class RoadSummary(BaseModel):
    node_count: int
    edge_count: int
    total_length_km: float
    road_class_length_km: dict[str, float]
    weakly_connected_components: int
    largest_scc_node_fraction: float = Field(description="Share of nodes in the largest strongly connected component")
    provider: str | None


class FacilitySummary(BaseModel):
    facility_count: int
    by_category: dict[str, int]
    candidate_hub_count: int
    authority_verified_shelters: int


class FloodSummary(BaseModel):
    polygon_count: int
    sfha_area_km2: float
    area_km2_by_zone: dict[str, float]
    covered_area_fraction: float | None
    dfirm_ids: list[str]
    tracts_intersecting_sfha: int | None
    tracts_in_covered_area: int | None


class RegionSummary(BaseModel):
    region_id: str
    name: str
    provenance: Provenance = Provenance.derived
    population: PopulationSummary | None
    roads: RoadSummary | None
    facilities: FacilitySummary | None
    flood: FloodSummary | None
    unavailable_datasets: list[str]
    generated_at: str
