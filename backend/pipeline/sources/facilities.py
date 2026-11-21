"""Facility acquisition: OpenStreetMap (OSMnx features) with Overture Places fallback."""

from __future__ import annotations

import logging
from pathlib import Path

from pipeline.context import PipelineContext
from pipeline.http import SourceUnavailableError, is_cached, write_sidecar
from pipeline.sources import catalog, overture

logger = logging.getLogger(__name__)

OSM_TAGS: dict[str, list[str] | bool] = {
    "amenity": [
        "hospital", "clinic", "doctors", "community_centre", "library", "school", "fire_station",
        "police", "townhall", "social_facility", "shelter", "social_centre",
    ],
    "healthcare": ["hospital", "clinic"],
    "social_facility": ["shelter"],
}

PLACE_COLUMNS = ["id", "geometry", "names", "basic_category", "taxonomy", "confidence", "operating_status",
                 "addresses", "sources"]


def osm_path(ctx: PipelineContext) -> Path:
    return ctx.region_raw / "facilities" / "osm_facilities.geojson"


def overture_path(ctx: PipelineContext) -> Path:
    return ctx.region_raw / "facilities" / "overture_places.parquet"


def raw_facilities(ctx: PipelineContext) -> tuple[str, Path] | None:
    if is_cached(osm_path(ctx)):
        return "osm", osm_path(ctx)
    if is_cached(overture_path(ctx)):
        return "overture", overture_path(ctx)
    return None


def _osm(ctx: PipelineContext, bbox: tuple[float, float, float, float]) -> Path:
    import osmnx as ox

    ox.settings.use_cache = True
    ox.settings.cache_folder = str(ctx.settings.data_dir / "cache" / "osmnx")
    try:
        gdf = ox.features_from_bbox(bbox, tags=OSM_TAGS)
    except Exception as exc:
        raise SourceUnavailableError(f"OSMnx features failed: {type(exc).__name__}: {exc}") from exc
    dest = osm_path(ctx)
    dest.parent.mkdir(parents=True, exist_ok=True)
    gdf = gdf.reset_index()
    keep = [c for c in gdf.columns if c in {
        "element", "id", "geometry", "name", "amenity", "healthcare", "social_facility", "shelter_type",
        "addr:housenumber", "addr:street", "addr:city", "addr:postcode", "operator", "emergency",
    }]
    gdf[keep].to_file(dest, driver="GeoJSON")
    write_sidecar(dest, provider="osm", bbox=list(bbox), tags=OSM_TAGS, source=catalog.OSM_OVERPASS)
    return dest


def _overture(ctx: PipelineContext, bbox: tuple[float, float, float, float]) -> Path:
    release = overture.latest_release()
    dest = overture_path(ctx)
    n = overture.extract_bbox(release, "places", "place", bbox, dest, PLACE_COLUMNS)
    write_sidecar(dest, provider="overture", release=release, bbox=list(bbox), rows=n,
                  source=catalog.overture(release, "places"))
    return dest


def download_facilities(ctx: PipelineContext, bbox: tuple[float, float, float, float], provider: str = "auto") -> tuple[str, Path]:
    existing = raw_facilities(ctx)
    if existing and not ctx.force and provider in ("auto", existing[0]):
        logger.info("cached facilities: %s", existing[1].name)
        return existing
    order = ["osm", "overture"] if provider == "auto" else [provider]
    errors = []
    for name in order:
        try:
            return name, (_osm if name == "osm" else _overture)(ctx, bbox)
        except SourceUnavailableError as exc:
            logger.warning("Facility provider %s unavailable: %s", name, exc)
            errors.append(f"{name}: {exc}")
    raise SourceUnavailableError("All facility providers failed: " + "; ".join(errors))
