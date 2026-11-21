"""Regions, study area and census tract geometry."""

from __future__ import annotations

from typing import Any

from app.datasets import DATASETS
from app.regions import RegionDefinition, get_region, load_regions
from app.schemas.census import CensusTract
from app.schemas.common import Feature, FeatureCollection
from app.schemas.region import DatasetState, DatasetStatus, GeographicRegion
from app.services.repository import DataRepository
from app.services.serialization import clean_value, geometry_to_geojson, paginate

TRACT_FIELDS = list(CensusTract.model_fields)


def dataset_statuses(repo: DataRepository, region_id: str) -> list[DatasetStatus]:
    manifest = repo.manifest(region_id) or {}
    entries = manifest.get("datasets", {})
    out: list[DatasetStatus] = []
    for key, spec in DATASETS.items():
        path = repo.path(region_id, key)
        entry = entries.get(key, {})
        if path.exists():
            state = DatasetState.available
        elif entry.get("state") == "invalid":
            state = DatasetState.invalid
        else:
            state = DatasetState.missing
        out.append(
            DatasetStatus(
                dataset=key,
                title=spec.title,
                state=state,
                record_count=entry.get("record_count") if path.exists() else None,
                provenance=entry.get("provenance"),
                file=f"data/processed/{region_id}/{spec.filename}",
                size_bytes=path.stat().st_size if path.exists() else None,
                generated_at=entry.get("generated_at"),
                provider=entry.get("provider"),
                sources=entry.get("sources", []),
                notes=entry.get("notes", []),
            )
        )
    return out


def region_model(repo: DataRepository, region: RegionDefinition) -> GeographicRegion:
    manifest = repo.manifest(region.region_id) or {}
    return GeographicRegion(
        **region.model_dump(exclude={"road_buffer_m"}),
        study_area_bbox=manifest.get("study_area_bbox"),
        datasets=dataset_statuses(repo, region.region_id),
        pipeline_generated_at=manifest.get("generated_at"),
    )


def list_regions(repo: DataRepository) -> list[GeographicRegion]:
    return [region_model(repo, r) for r in load_regions().values()]


def get_region_model(repo: DataRepository, region_id: str) -> GeographicRegion:
    return region_model(repo, get_region(region_id))


def tracts_collection(
    repo: DataRepository,
    region_id: str,
    limit: int,
    offset: int,
    include_geometry: bool = True,
    county_fips: str | None = None,
    simplify_m: float | None = None,
) -> FeatureCollection[CensusTract]:
    region = get_region(region_id)
    gdf = repo.load(region_id, "tracts")
    if county_fips:
        gdf = gdf[gdf["county_fips"] == county_fips]
    gdf = gdf.sort_values("geoid")
    page, info = paginate(gdf, limit, offset)
    geoms = page.geometry
    if include_geometry and simplify_m:
        geoms = page.to_crs(region.analysis_crs).geometry.simplify(simplify_m).to_crs(4326)
    features: list[Feature[CensusTract]] = []
    for (_, row), geom in zip(page.iterrows(), geoms):
        props: dict[str, Any] = {f: clean_value(row.get(f)) for f in TRACT_FIELDS if f != "internal_point"}
        lon, lat = clean_value(row.get("intpt_lon")), clean_value(row.get("intpt_lat"))
        props["internal_point"] = (lon, lat) if lon is not None and lat is not None else None
        features.append(
            Feature[CensusTract](
                id=row["geoid"],
                geometry=geometry_to_geojson(geom) if include_geometry else None,
                properties=CensusTract(**props),
            )
        )
    return FeatureCollection[CensusTract](
        features=features,
        page=info,
        provenance=repo.provenance(region_id, "tracts"),
        sources=repo.sources(region_id, "tracts"),
    )
