"""HTTP helpers: retrying session, idempotent downloads with provenance sidecars,
and paginated ArcGIS REST feature queries."""

from __future__ import annotations

import hashlib
import json
import logging
import time
from pathlib import Path
from typing import Any, Callable, Iterator

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from app.datasets import utc_now

logger = logging.getLogger(__name__)

USER_AGENT = "crisees-data-pipeline/0.1 (research; flood evacuation accessibility)"
DEFAULT_TIMEOUT = (15, 120)


class SourceUnavailableError(RuntimeError):
    """An upstream source could not be reached or returned unusable data."""


def session() -> requests.Session:
    s = requests.Session()
    retry = Retry(
        total=4,
        backoff_factor=1.5,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=("GET", "HEAD", "POST"),
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry)
    s.mount("https://", adapter)
    s.mount("http://", adapter)
    s.headers["User-Agent"] = USER_AGENT
    return s


def sidecar_path(path: Path) -> Path:
    return path.with_name(path.name + ".source.json")


def write_sidecar(path: Path, **meta: Any) -> None:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    payload = {"file": path.name, "bytes": path.stat().st_size, "sha256": digest.hexdigest(), **meta}
    payload.setdefault("retrieved_at", utc_now())
    sidecar_path(path).write_text(json.dumps(payload, indent=2, default=str))


def read_sidecar(path: Path) -> dict[str, Any]:
    sc = sidecar_path(path)
    return json.loads(sc.read_text()) if sc.exists() else {}


def is_cached(path: Path) -> bool:
    """A cached file counts only if both it and its provenance sidecar exist."""
    return path.exists() and path.stat().st_size > 0 and sidecar_path(path).exists()


def download_file(
    url: str,
    dest: Path,
    *,
    force: bool = False,
    line_filter: Callable[[bytes], bool] | None = None,
    keep_header: bool = True,
    expect_prefix: bytes | None = None,
    **meta: Any,
) -> Path:
    """Stream ``url`` to ``dest`` atomically. Skips if already cached.

    ``line_filter`` keeps only matching lines of a text file (plus the
    header line), e.g. to retain Texas tracts from a national ACS table.
    ``expect_prefix`` guards against error pages served with HTTP 200 (e.g.
    a web-application-firewall rejection page): the body must start with it.
    """
    if is_cached(dest) and not force:
        logger.info("cached: %s", dest.name)
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(dest.name + ".part")
    logger.info("downloading %s", url)
    t0 = time.time()
    try:
        with session().get(url, stream=True, timeout=DEFAULT_TIMEOUT) as r:
            if r.status_code != 200:
                raise SourceUnavailableError(f"HTTP {r.status_code} for {url}")
            with tmp.open("wb") as fh:
                if line_filter is None:
                    for chunk in r.iter_content(1 << 20):
                        fh.write(chunk)
                else:
                    first = True
                    for line in r.iter_lines():
                        if (first and keep_header) or line_filter(line):
                            fh.write(line + b"\n")
                        first = False
    except requests.RequestException as exc:
        tmp.unlink(missing_ok=True)
        raise SourceUnavailableError(f"{type(exc).__name__} for {url}: {exc}") from exc
    except SourceUnavailableError:
        tmp.unlink(missing_ok=True)
        raise
    if expect_prefix is not None:
        with tmp.open("rb") as fh:
            head = fh.read(len(expect_prefix))
        if head != expect_prefix:
            tmp.unlink(missing_ok=True)
            raise SourceUnavailableError(
                f"Unexpected content from {url} (starts with {head[:40]!r}); possibly an error page"
            )
    tmp.replace(dest)
    write_sidecar(dest, url=url, filtered=line_filter is not None, **meta)
    logger.info("saved %s (%.1f MB, %.0fs)", dest.name, dest.stat().st_size / 1e6, time.time() - t0)
    return dest


def arcgis_query(
    layer_url: str,
    *,
    where: str = "1=1",
    envelope: tuple[float, float, float, float] | None = None,
    out_fields: str = "*",
    return_geometry: bool = True,
    page_size: int = 1000,
    max_records: int = 200_000,
) -> Iterator[dict[str, Any]]:
    """Yield GeoJSON features from an ArcGIS REST layer ``/query`` endpoint (EPSG:4326 output)."""
    s = session()
    offset = 0
    while True:
        params: dict[str, Any] = {
            "where": where,
            "outFields": out_fields,
            "returnGeometry": str(return_geometry).lower(),
            "outSR": 4326,
            "f": "geojson",
            "resultOffset": offset,
            "resultRecordCount": page_size,
            "orderByFields": "",
        }
        if envelope:
            params.update(
                geometry=",".join(str(c) for c in envelope),
                geometryType="esriGeometryEnvelope",
                inSR=4326,
                spatialRel="esriSpatialRelIntersects",
            )
        try:
            r = s.get(f"{layer_url}/query", params=params, timeout=DEFAULT_TIMEOUT)
        except requests.RequestException as exc:
            raise SourceUnavailableError(f"{type(exc).__name__} for {layer_url}: {exc}") from exc
        if r.status_code != 200:
            raise SourceUnavailableError(f"HTTP {r.status_code} for {layer_url}")
        try:
            data = r.json()
        except ValueError as exc:
            raise SourceUnavailableError(f"Non-JSON response from {layer_url}") from exc
        if "error" in data:
            raise SourceUnavailableError(f"ArcGIS error from {layer_url}: {data['error']}")
        feats = data.get("features", [])
        yield from feats
        offset += len(feats)
        exceeded = data.get("exceededTransferLimit") or data.get("properties", {}).get("exceededTransferLimit")
        if not feats or (not exceeded and len(feats) < page_size) or offset >= max_records:
            break


def arcgis_layer_info(layer_url: str) -> dict[str, Any]:
    try:
        r = session().get(layer_url, params={"f": "json"}, timeout=DEFAULT_TIMEOUT)
        data = r.json()
    except (requests.RequestException, ValueError) as exc:
        raise SourceUnavailableError(f"{type(exc).__name__} for {layer_url}: {exc}") from exc
    if "error" in data:
        raise SourceUnavailableError(f"ArcGIS error from {layer_url}: {data['error']}")
    return data


def save_feature_collection(features: list[dict[str, Any]], dest: Path, **meta: Any) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(dest.name + ".part")
    tmp.write_text(json.dumps({"type": "FeatureCollection", "features": features}))
    tmp.replace(dest)
    write_sidecar(dest, feature_count=len(features), **meta)
    return dest
