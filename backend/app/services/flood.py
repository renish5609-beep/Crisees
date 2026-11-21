"""FEMA regulatory flood hazard areas and their coverage extent."""

from __future__ import annotations



from app.core.errors import DatasetNotAvailableError
from app.regions import get_region
from app.schemas.common import Feature, FeatureCollection
from app.schemas.flood import FloodCoverage, FloodHazardArea
from app.services.repository import DataRepository
from app.services.serialization import clean_value, geometry_to_geojson, paginate

HAZARD_FIELDS = list(FloodHazardArea.model_fields)


class FloodHazardCollection(FeatureCollection[FloodHazardArea]):
    coverage: FloodCoverage | None = None
    disclaimer: str = (
        "FEMA flood zones are regulatory, probabilistic hazard designations (e.g. 1% annual chance). "
        "They are not observed or real-time flooding, and areas outside the covered extent have no data, "
        "not zero hazard."
    )


def flood_coverage(repo: DataRepository, region_id: str) -> FloodCoverage | None:
    entry = repo.manifest_entry(region_id, "flood_coverage")
    if not entry:
        return None
    extra = entry.get("extra", {})
    return FloodCoverage(
        covered_area_fraction=extra.get("covered_area_fraction"),
        dfirm_ids=extra.get("dfirm_ids", []),
        method=extra.get("method", ""),
    )


def flood_collection(
    repo: DataRepository,
    region_id: str,
    limit: int,
    offset: int,
    sfha_only: bool = False,
    zones: list[str] | None = None,
    simplify_m: float | None = None,
) -> FloodHazardCollection:
    region = get_region(region_id)
    gdf = repo.load(region_id, "flood_hazards")
    if sfha_only:
        gdf = gdf[gdf["is_sfha"] == True]  # noqa: E712 - nullable boolean column
    if zones:
        gdf = gdf[gdf["flood_zone"].isin(zones)]
    gdf = gdf.sort_values("hazard_id")
    page, info = paginate(gdf, limit, offset)
    geoms = page.geometry
    if simplify_m:
        geoms = page.to_crs(region.analysis_crs).geometry.simplify(simplify_m).to_crs(4326)
    features = [
        Feature[FloodHazardArea](
            id=row.hazard_id,
            geometry=geometry_to_geojson(geom),
            properties=FloodHazardArea(**{f: clean_value(getattr(row, f, None)) for f in HAZARD_FIELDS}),
        )
        for row, geom in zip(page.itertuples(index=False), geoms)
    ]
    try:
        coverage = flood_coverage(repo, region_id)
    except DatasetNotAvailableError:
        coverage = None
    return FloodHazardCollection(
        features=features,
        page=info,
        provenance=repo.provenance(region_id, "flood_hazards"),
        sources=repo.sources(region_id, "flood_hazards"),
        coverage=coverage,
    )


