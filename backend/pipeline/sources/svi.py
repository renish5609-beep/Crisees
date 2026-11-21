"""CDC/ATSDR Social Vulnerability Index (tract level).

Primary: official CDC state CSV (SVI 2022). Fallback: an ArcGIS Online copy
of the CDC SVI 2020 tract table. The provider actually used is recorded.
"""

from __future__ import annotations

import csv
import logging
from pathlib import Path

from pipeline.context import PipelineContext
from pipeline.http import SourceUnavailableError, arcgis_query, download_file, is_cached, read_sidecar, write_sidecar
from pipeline.sources import catalog

logger = logging.getLogger(__name__)

SVI_FIELDS = [
    "FIPS", "STCNTY", "RPL_THEMES", "RPL_THEME1", "RPL_THEME2", "RPL_THEME3", "RPL_THEME4",
    "EP_POV150", "EP_UNEMP", "EP_NOHSDP", "EP_UNINSUR", "EP_AGE65", "EP_AGE17", "EP_DISABL",
    "EP_SNGPNT", "EP_LIMENG", "EP_MINRTY", "EP_MUNIT", "EP_MOBILE", "EP_CROWD", "EP_NOVEH",
    "EP_GROUPQ", "F_TOTAL", "E_TOTPOP",
]


def svi_path(ctx: PipelineContext) -> Path:
    return ctx.region_raw / "svi" / "svi_tracts.csv"


def svi_metadata(ctx: PipelineContext) -> dict:
    return read_sidecar(svi_path(ctx))


def _official(ctx: PipelineContext, dest: Path) -> Path:
    src = catalog.SVI_CDC_2022
    counties = tuple(ctx.region.county_geoids)
    tmp = download_file(src["url"], dest.with_name("svi_cdc_state.csv"), force=ctx.force, source=src)
    with tmp.open(newline="") as fh, dest.open("w", newline="") as out:
        reader = csv.DictReader(fh)
        writer = csv.DictWriter(out, fieldnames=SVI_FIELDS, extrasaction="ignore")
        writer.writeheader()
        for row in reader:
            if str(row.get("STCNTY", "")).zfill(5) in counties:
                writer.writerow(row)
    write_sidecar(dest, provider="cdc_official", svi_year=2022, source=src)
    return dest


def _mirror(ctx: PipelineContext, dest: Path) -> Path:
    src = catalog.SVI_ESRI_MIRROR_2020
    where = " OR ".join(f"STCOFIPS='{c}'" for c in ctx.region.county_geoids)
    feats = list(arcgis_query(src["url"], where=where, out_fields=",".join(SVI_FIELDS), return_geometry=False))
    if not feats:
        raise SourceUnavailableError("SVI mirror returned no features for the region's counties")
    with dest.open("w", newline="") as out:
        writer = csv.DictWriter(out, fieldnames=SVI_FIELDS, extrasaction="ignore")
        writer.writeheader()
        for f in feats:
            writer.writerow(f["properties"])
    write_sidecar(dest, provider="esri_mirror", svi_year=2020, query=where, source=src)
    return dest


def download_svi(ctx: PipelineContext) -> Path:
    dest = svi_path(ctx)
    if is_cached(dest) and not ctx.force:
        logger.info("cached: %s", dest.name)
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    errors = []
    for name, fn in (("cdc_official", _official), ("esri_mirror", _mirror)):
        try:
            path = fn(ctx, dest)
            logger.info("SVI retrieved via %s", name)
            return path
        except SourceUnavailableError as exc:
            logger.warning("SVI provider %s unavailable: %s", name, exc)
            errors.append(f"{name}: {exc}")
    raise SourceUnavailableError("All SVI providers failed: " + "; ".join(errors))
