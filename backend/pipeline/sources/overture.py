"""Overture Maps (GeoParquet on public S3) bbox extracts via PyArrow.

Overture's transportation theme is derived from OpenStreetMap and carries
OSM way ids in ``sources[].record_id``; it is used as a fallback when the
Overpass API (OSMnx) is unreachable. Places are used as a fallback facility
source. Requires no credentials (anonymous S3).
"""

from __future__ import annotations

import logging
from pathlib import Path

from pipeline.http import SourceUnavailableError

logger = logging.getLogger(__name__)

BUCKET = "overturemaps-us-west-2"
REGION = "us-west-2"


def _fs():  # type: ignore[no-untyped-def]
    import pyarrow.fs as pafs

    return pafs.S3FileSystem(anonymous=True, region=REGION, connect_timeout=20, request_timeout=120)


def latest_release() -> str:
    """Newest release, unless CRISEES_OVERTURE_RELEASE pins one (reproducible builds)."""
    import os

    import pyarrow.fs as pafs

    pinned = os.environ.get("CRISEES_OVERTURE_RELEASE")
    if pinned:
        return pinned

    try:
        infos = _fs().get_file_info(pafs.FileSelector(f"{BUCKET}/release/", recursive=False))
    except OSError as exc:
        raise SourceUnavailableError(f"Cannot list Overture releases: {exc}") from exc
    releases = sorted(i.base_name for i in infos if i.type == pafs.FileType.Directory)
    if not releases:
        raise SourceUnavailableError("No Overture releases found")
    return releases[-1]


def extract_bbox(
    release: str,
    theme: str,
    type_: str,
    bbox: tuple[float, float, float, float],
    dest: Path,
    columns: list[str] | None = None,
) -> int:
    """Write rows whose bbox intersects ``bbox`` to ``dest`` (GeoParquet, WKB geometry)."""
    import pyarrow.compute as pc
    import pyarrow.dataset as ds
    import pyarrow.parquet as pq

    w, s, e, n = bbox
    path = f"{BUCKET}/release/{release}/theme={theme}/type={type_}/"
    try:
        dataset = ds.dataset(path, filesystem=_fs(), format="parquet")
        flt = (
            (pc.field("bbox", "xmin") < e)
            & (pc.field("bbox", "xmax") > w)
            & (pc.field("bbox", "ymin") < n)
            & (pc.field("bbox", "ymax") > s)
        )
        table = dataset.to_table(filter=flt, columns=columns)
    except OSError as exc:
        raise SourceUnavailableError(f"Overture read failed for {theme}/{type_}: {exc}") from exc
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(dest.name + ".part")
    pq.write_table(table, tmp, compression="zstd")
    tmp.replace(dest)
    logger.info("Overture %s/%s: %d rows -> %s", theme, type_, table.num_rows, dest.name)
    return table.num_rows
