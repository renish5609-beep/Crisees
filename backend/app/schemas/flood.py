from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class HazardEvidenceType(str, Enum):
    """Kinds of flood information, which must never be conflated."""

    fema_regulatory = "fema_regulatory"  # FEMA FIRM/NFHL mapped flood zone (probabilistic, regulatory)
    observed = "observed"  # actually observed inundation (none ingested in Phase 1)
    simulated = "simulated"  # hypothetical scenario road closures (Phase 2)


class FloodHazardArea(BaseModel):
    hazard_id: str
    evidence_type: HazardEvidenceType = HazardEvidenceType.fema_regulatory
    flood_zone: str | None = Field(description="FEMA FLD_ZONE (A, AE, AO, X, ...)")
    zone_subtype: str | None = None
    is_sfha: bool | None = Field(description="Special Flood Hazard Area (1% annual chance)")
    annual_chance_category: str = Field(description="'1pct', '0.2pct', 'minimal', or 'other'")
    static_bfe_ft: float | None = None
    dfirm_id: str | None = None
    version_id: str | None = None
    source_citation: str | None = None
    area_m2: float | None = None
    source_id: str


class FloodCoverage(BaseModel):
    """What part of the study area the ingested flood data actually covers.

    Absence of a mapped flood polygon outside the covered area means *no
    data*, not *no hazard*.
    """

    covered_area_fraction: float | None
    dfirm_ids: list[str]
    method: str
