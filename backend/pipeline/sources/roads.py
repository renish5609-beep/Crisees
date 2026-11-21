"""Drivable road network acquisition.

Provider order:
1. ``osmnx``: OSMnx ``graph_from_bbox(network_type="drive")`` against the
   Overpass API; raw graph saved as GraphML.
2. ``overture``: Overture transportation segments (OSM-derived) for the same
   bbox; converted to an OSMnx-compatible graph during processing.
"""

from __future__ import annotations

import logging
from pathlib import Path

from pipeline.context import PipelineContext
from pipeline.http import SourceUnavailableError, is_cached, read_sidecar, write_sidecar
from pipeline.sources import catalog, overture

logger = logging.getLogger(__name__)

SEGMENT_COLUMNS = [
    "id", "geometry", "names", "subtype", "class", "subclass", "connectors",
    "access_restrictions", "speed_limits", "road_flags", "sources",
]


def osmnx_path(ctx: PipelineContext) -> Path:
    return ctx.region_raw / "roads" / "osmnx_drive.graphml"


def overture_path(ctx: PipelineContext) -> Path:
    return ctx.region_raw / "roads" / "overture_segments.parquet"


def raw_roads(ctx: PipelineContext) -> tuple[str, Path] | None:
    """Return (provider, path) of the best available raw road download."""
    if is_cached(osmnx_path(ctx)):
        return "osmnx", osmnx_path(ctx)
    if is_cached(overture_path(ctx)):
        return "overture", overture_path(ctx)
    return None


def roads_metadata(path: Path) -> dict:
    return read_sidecar(path)


def _osmnx(ctx: PipelineContext, bbox: tuple[float, float, float, float]) -> Path:
    import osmnx as ox

    ox.settings.use_cache = True
    ox.settings.cache_folder = str(ctx.settings.data_dir / "cache" / "osmnx")
    ox.settings.requests_timeout = 180
    dest = osmnx_path(ctx)
    try:
        G = ox.graph_from_bbox(bbox, network_type="drive", simplify=True, retain_all=False, truncate_by_edge=True)
    except Exception as exc:  # osmnx raises various request/response errors
        raise SourceUnavailableError(f"OSMnx/Overpass failed: {type(exc).__name__}: {exc}") from exc
    dest.parent.mkdir(parents=True, exist_ok=True)
    ox.save_graphml(G, dest)
    write_sidecar(dest, provider="osmnx", bbox=list(bbox), network_type="drive", osmnx_version=ox.__version__,
                  source=catalog.OSM_OVERPASS)
    return dest


def _overture(ctx: PipelineContext, bbox: tuple[float, float, float, float]) -> Path:
    release = overture.latest_release()
    dest = overture_path(ctx)
    n = overture.extract_bbox(release, "transportation", "segment", bbox, dest, SEGMENT_COLUMNS)
    if n == 0:
        raise SourceUnavailableError("Overture returned no segments")
    write_sidecar(dest, provider="overture", release=release, bbox=list(bbox), rows=n,
                  source=catalog.overture(release, "transportation"))
    return dest


def download_roads(ctx: PipelineContext, bbox: tuple[float, float, float, float], provider: str = "auto") -> tuple[str, Path]:
    existing = raw_roads(ctx)
    if existing and not ctx.force and provider in ("auto", existing[0]):
        logger.info("cached roads: %s", existing[1].name)
        return existing
    order = ["osmnx", "overture"] if provider == "auto" else [provider]
    errors = []
    for name in order:
        try:
            path = (_osmnx if name == "osmnx" else _overture)(ctx, bbox)
            return name, path
        except SourceUnavailableError as exc:
            logger.warning("Road provider %s unavailable: %s", name, exc)
            errors.append(f"{name}: {exc}")
    raise SourceUnavailableError("All road providers failed: " + "; ".join(errors))
