"""Emergency-relevant facilities and derived candidate pickup hubs."""

from __future__ import annotations

from app.schemas.common import Feature, FeatureCollection
from app.schemas.facilities import CandidatePickupHub, EmergencyFacility
from app.services.repository import DataRepository
from app.services.serialization import clean_value, geometry_to_geojson, paginate

FACILITY_FIELDS = list(EmergencyFacility.model_fields)
HUB_FIELDS = list(CandidatePickupHub.model_fields)


def facilities_collection(
    repo: DataRepository,
    region_id: str,
    limit: int,
    offset: int,
    categories: list[str] | None = None,
) -> FeatureCollection[EmergencyFacility]:
    gdf = repo.load(region_id, "facilities")
    if categories:
        gdf = gdf[gdf["category"].isin(categories)]
    gdf = gdf.sort_values("facility_id")
    page, info = paginate(gdf, limit, offset)
    features = [
        Feature[EmergencyFacility](
            id=row.facility_id,
            geometry=geometry_to_geojson(row.geometry),
            properties=EmergencyFacility(**{f: clean_value(getattr(row, f, None)) for f in FACILITY_FIELDS}),
        )
        for row in page.itertuples(index=False)
    ]
    return FeatureCollection[EmergencyFacility](
        features=features,
        page=info,
        provenance=repo.provenance(region_id, "facilities"),
        sources=repo.sources(region_id, "facilities"),
    )


def candidate_hubs_collection(
    repo: DataRepository, region_id: str, limit: int, offset: int
) -> FeatureCollection[CandidatePickupHub]:
    gdf = repo.load(region_id, "candidate_hubs").sort_values("hub_id")
    page, info = paginate(gdf, limit, offset)
    features = [
        Feature[CandidatePickupHub](
            id=row.hub_id,
            geometry=geometry_to_geojson(row.geometry),
            properties=CandidatePickupHub(**{f: clean_value(getattr(row, f, None)) for f in HUB_FIELDS}),
        )
        for row in page.itertuples(index=False)
    ]
    return FeatureCollection[CandidatePickupHub](
        features=features,
        page=info,
        provenance=repo.provenance(region_id, "candidate_hubs"),
        sources=repo.sources(region_id, "candidate_hubs"),
    )
