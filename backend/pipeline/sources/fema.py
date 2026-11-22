"""FEMA flood hazard zones (S_FLD_HAZ_AR) and FIRM panel extents (S_FIRM_PAN).

Primary: FEMA's official NFHL MapServer. Fallback: an ArcGIS Online copy of
the FIRM database for DFIRM 48157C (Fort Bend County), which only covers
part of the pilot area. Panel extents are downloaded alongside hazard
polygons so coverage gaps are explicit instead of being read as "no hazard".
"""

from __future__ import annotations

import logging
from pathlib import Path

from pipeline.context import PipelineContext
from pipeline.http import SourceUnavailableError, arcgis_query, is_cached, read_sidecar, save_feature_collection
from pipeline.sources import catalog

logger = logging.getLogger(__name__)

HAZARD_FIELDS = "DFIRM_ID,VERSION_ID,FLD_AR_ID,STUDY_TYP,FLD_ZONE,ZONE_SUBTY,SFHA_TF,STATIC_BFE,DEPTH,SOURCE_CIT"
PANEL_FIELDS = "DFIRM_ID,VERSION_ID,FIRM_PAN,PANEL_TYP,EFF_DATE"

PROVIDERS = {
    "fema_official": {
        "hazard": "https://hazards.fema.gov/arcgis/rest/services/public/NFHL/MapServer/28",
        "panels": "https://hazards.fema.gov/arcgis/rest/services/public/NFHL/MapServer/3",
        "source": catalog.FEMA_NFHL_OFFICIAL,
    },
    "fema_mirror_48157C": {
        "hazard": "https://services1.arcgis.com/cTNi34MxOdcfum3A/ArcGIS/rest/services/Map_TX_WFL1/FeatureServer/24",
        "panels": "https://services1.arcgis.com/cTNi34MxOdcfum3A/ArcGIS/rest/services/Map_TX_WFL1/FeatureServer/25",
        "source": catalog.FEMA_FIRM_MIRROR_FORT_BEND,
    },
}


def hazard_path(ctx: PipelineContext) -> Path:
    return ctx.region_raw / "fema" / "s_fld_haz_ar.geojson"


def panel_path(ctx: PipelineContext) -> Path:
    return ctx.region_raw / "fema" / "s_firm_pan.geojson"


def fema_metadata(ctx: PipelineContext) -> dict:
    return read_sidecar(hazard_path(ctx))


def download_flood(ctx: PipelineContext, bbox: tuple[float, float, float, float], provider: str = "auto") -> tuple[Path, Path]:
    hz, pn = hazard_path(ctx), panel_path(ctx)
    if is_cached(hz) and is_cached(pn) and not ctx.force:
        logger.info("cached: %s, %s", hz.name, pn.name)
        return hz, pn
    errors = []
    for name, cfg in PROVIDERS.items():
        if provider not in ("auto", name):
            continue
        try:
            hazards = list(arcgis_query(cfg["hazard"], envelope=bbox, out_fields="*"))
            panels = list(arcgis_query(cfg["panels"], envelope=bbox, out_fields="*"))
        except SourceUnavailableError as exc:
            logger.warning("FEMA provider %s unavailable: %s", name, exc)
            errors.append(f"{name}: {exc}")
            continue
        if not hazards:
            errors.append(f"{name}: no hazard polygons intersect bbox")
            continue
        meta = dict(provider=name, bbox=list(bbox), layer_url=cfg["hazard"], source=cfg["source"])
        save_feature_collection(hazards, hz, **meta)
        save_feature_collection(panels, pn, **{**meta, "layer_url": cfg["panels"]})
        logger.info("FEMA via %s: %d hazard polygons, %d panels", name, len(hazards), len(panels))
        return hz, pn
    raise SourceUnavailableError("All FEMA providers failed: " + "; ".join(errors))
