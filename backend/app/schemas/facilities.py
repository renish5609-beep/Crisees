from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class FacilityCategory(str, Enum):
    shelter = "shelter"
    hospital = "hospital"
    clinic = "clinic"
    community_centre = "community_centre"
    library = "library"
    school = "school"
    fire_station = "fire_station"
    police = "police"
    townhall = "townhall"
    social_facility = "social_facility"


class VerificationStatus(str, Enum):
    # A feature present in an open map dataset. It is NOT an approved
    # emergency shelter unless an emergency-management authority says so.
    mapped_unverified = "mapped_unverified"
    # Confirmed against an authoritative designated-shelter list (none ingested in Phase 1).
    authority_verified = "authority_verified"


class EmergencyFacility(BaseModel):
    facility_id: str
    name: str | None
    category: FacilityCategory
    source_category: str = Field(description="Raw category/tag from the source (e.g. 'amenity=library')")
    lon: float
    lat: float
    address: str | None = None
    verification_status: VerificationStatus = VerificationStatus.mapped_unverified
    is_designated_evacuation_shelter: bool | None = Field(
        default=None, description="None = unknown. Phase 1 never asserts True without an authoritative list."
    )
    source_id: str
    source_record_id: str
    confidence: float | None = Field(default=None, description="Source-provided existence confidence (Overture)")


class CandidatePickupHub(BaseModel):
    """A *candidate* location for a temporary pickup hub.

    Derived from public facilities that typically have parking/frontage and
    public access. Candidacy is a planning hypothesis, not an operational
    designation; Phase 2 optimisation chooses among candidates.
    """

    hub_id: str
    facility_id: str
    name: str | None
    category: FacilityCategory
    lon: float
    lat: float
    candidacy_basis: str
    nearest_node_id: int | None = None
    snap_distance_m: float | None = None
    status: str = "candidate_unvalidated"
