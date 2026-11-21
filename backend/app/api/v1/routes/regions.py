"""/api/v1/regions endpoints."""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Path, Query

from app.api.deps import Page, Repo
from app.core.errors import CriseesError
from app.schemas.census import CensusTract, TractDemographics
from app.schemas.common import FeatureCollection, RecordPage
from app.schemas.facilities import CandidatePickupHub, EmergencyFacility, FacilityCategory
from app.schemas.region import DatasetStatus, GeographicRegion
from app.schemas.summary import RegionSummary
from app.services import demographics, facilities, flood, geography, roads, summary

router = APIRouter(prefix="/regions", tags=["regions"])

RegionId = Annotated[str, Path(pattern=r"^[a-z0-9][a-z0-9-]*$", description="e.g. houston-sw-pilot")]


class BadRequestError(CriseesError):
    status_code = 400
    code = "bad_request"


def _parse_bbox(bbox: str | None) -> tuple[float, float, float, float] | None:
    if bbox is None:
        return None
    try:
        w, s, e, n = (float(x) for x in bbox.split(","))
    except ValueError:
        raise BadRequestError("bbox must be 'west,south,east,north' in lon/lat degrees.", bbox=bbox) from None
    if not (-180 <= w < e <= 180 and -90 <= s < n <= 90):
        raise BadRequestError("bbox coordinates out of range or inverted.", bbox=bbox)
    return (w, s, e, n)


def _csv(value: str | None) -> list[str] | None:
    return [v.strip() for v in value.split(",") if v.strip()] if value else None


@router.get("", response_model=list[GeographicRegion], summary="List configured study regions")
def list_regions(repo: Repo) -> list[GeographicRegion]:
    return geography.list_regions(repo)


@router.get("/{region_id}", response_model=GeographicRegion, summary="Region metadata and dataset status")
def get_region(region_id: RegionId, repo: Repo) -> GeographicRegion:
    return geography.get_region_model(repo, region_id)


@router.get("/{region_id}/datasets", response_model=list[DatasetStatus], summary="Processed dataset inventory")
def get_datasets(region_id: RegionId, repo: Repo) -> list[DatasetStatus]:
    repo.region_dir(region_id)
    return geography.dataset_statuses(repo, region_id)


@router.get(
    "/{region_id}/tracts",
    response_model=FeatureCollection[CensusTract],
    summary="Census tract boundaries (GeoJSON)",
)
def get_tracts(
    region_id: RegionId,
    repo: Repo,
    page: Page,
    include_geometry: bool = True,
    county_fips: Annotated[str | None, Query(pattern=r"^\d{3}$")] = None,
    simplify_m: Annotated[float | None, Query(gt=0, le=500, description="Simplification tolerance, metres")] = None,
) -> FeatureCollection[CensusTract]:
    return geography.tracts_collection(
        repo, region_id, page.limit, page.offset, include_geometry, county_fips, simplify_m
    )


@router.get(
    "/{region_id}/demographics",
    response_model=RecordPage[TractDemographics],
    summary="ACS indicators (+ CDC SVI variables) per tract",
)
def get_demographics(
    region_id: RegionId,
    repo: Repo,
    page: Page,
    geoid: Annotated[str | None, Query(pattern=r"^\d{11}$")] = None,
    include_vulnerability: bool = True,
) -> RecordPage[TractDemographics]:
    return demographics.demographics_page(repo, region_id, page.limit, page.offset, geoid, include_vulnerability)


@router.get("/{region_id}/roads", response_model=FeatureCollection, summary="Drivable road network (GeoJSON)")
def get_roads(
    region_id: RegionId,
    repo: Repo,
    page: Page,
    layer: Literal["edges", "nodes"] = "edges",
    bbox: Annotated[str | None, Query(description="west,south,east,north (EPSG:4326)")] = None,
    road_class: Annotated[str | None, Query(description="Comma-separated OSM highway classes")] = None,
) -> FeatureCollection:
    return roads.roads_collection(
        repo, region_id, layer, page.limit, page.offset, _parse_bbox(bbox), _csv(road_class)
    )


@router.get(
    "/{region_id}/facilities",
    response_model=FeatureCollection[EmergencyFacility],
    summary="Mapped emergency-relevant facilities (unverified)",
)
def get_facilities(
    region_id: RegionId,
    repo: Repo,
    page: Page,
    category: Annotated[str | None, Query(description="Comma-separated FacilityCategory values")] = None,
) -> FeatureCollection[EmergencyFacility]:
    cats = _csv(category)
    if cats:
        valid = {c.value for c in FacilityCategory}
        bad = [c for c in cats if c not in valid]
        if bad:
            raise BadRequestError("Unknown facility category.", invalid=bad, valid=sorted(valid))
    return facilities.facilities_collection(repo, region_id, page.limit, page.offset, cats)


@router.get(
    "/{region_id}/candidate-hubs",
    response_model=FeatureCollection[CandidatePickupHub],
    summary="Candidate pickup hub locations (derived, unvalidated)",
)
def get_candidate_hubs(region_id: RegionId, repo: Repo, page: Page) -> FeatureCollection[CandidatePickupHub]:
    return facilities.candidate_hubs_collection(repo, region_id, page.limit, page.offset)


@router.get(
    "/{region_id}/flood-hazards",
    response_model=flood.FloodHazardCollection,
    summary="FEMA regulatory flood hazard zones (GeoJSON)",
)
def get_flood_hazards(
    region_id: RegionId,
    repo: Repo,
    page: Page,
    sfha_only: bool = False,
    zone: Annotated[str | None, Query(description="Comma-separated FEMA FLD_ZONE values")] = None,
    simplify_m: Annotated[float | None, Query(gt=0, le=500)] = None,
) -> flood.FloodHazardCollection:
    return flood.flood_collection(repo, region_id, page.limit, page.offset, sfha_only, _csv(zone), simplify_m)


@router.get("/{region_id}/summary", response_model=RegionSummary, summary="Region summary statistics")
def get_summary(region_id: RegionId, repo: Repo) -> RegionSummary:
    return summary.region_summary(repo, region_id)
