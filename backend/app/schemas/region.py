from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field

from app.schemas.common import Provenance, SourceAttribution


class DatasetState(str, Enum):
    available = "available"
    missing = "missing"
    invalid = "invalid"


class DatasetStatus(BaseModel):
    dataset: str
    title: str
    state: DatasetState
    record_count: int | None = None
    provenance: Provenance | None = None
    file: str | None = None
    size_bytes: int | None = None
    generated_at: str | None = None
    provider: str | None = Field(default=None, description="Which upstream provider produced the data.")
    sources: list[SourceAttribution] = []
    notes: list[str] = []


class GeographicRegion(BaseModel):
    region_id: str
    name: str
    description: str
    country: str
    state_fips: str
    state_abbr: str
    county_fips: list[str]
    county_names: dict[str, str]
    selection_bbox: tuple[float, float, float, float] = Field(description="[west, south, east, north], EPSG:4326")
    study_area_bbox: tuple[float, float, float, float] | None = Field(
        default=None, description="Bounds of the union of selected tracts (after processing)."
    )
    analysis_crs: str
    acs_year: int
    tiger_year: int
    hazard: str
    selection_rule: str
    justification: list[str]
    datasets: list[DatasetStatus] = []
    pipeline_generated_at: str | None = None
