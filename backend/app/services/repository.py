"""Read access to processed datasets with mtime-based caching."""

from __future__ import annotations

import gzip
import logging
import pickle
import threading
from pathlib import Path
from typing import Any

import geopandas as gpd
import pandas as pd

from app.core.config import Settings
from app.core.errors import DatasetCorruptError, DatasetNotAvailableError
from app.datasets import DATASETS, read_manifest, region_processed_dir
from app.regions import get_region
from app.schemas.common import Provenance, SourceAttribution

logger = logging.getLogger(__name__)

PIPELINE_HINT = (
    "Run `python scripts/download_data.py --region {region}` then "
    "`python scripts/process_data.py --region {region}` from the repository root."
)


class DataRepository:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._cache: dict[tuple[str, str], tuple[float, Any]] = {}
        self._lock = threading.Lock()

    # -- paths / manifest -------------------------------------------------
    def region_dir(self, region_id: str) -> Path:
        get_region(region_id)  # raises RegionNotFoundError
        return region_processed_dir(self.settings.processed_dir, region_id)

    def manifest(self, region_id: str) -> dict[str, Any] | None:
        return read_manifest(self.region_dir(region_id))

    def manifest_entry(self, region_id: str, key: str) -> dict[str, Any]:
        manifest = self.manifest(region_id) or {}
        return manifest.get("datasets", {}).get(key, {})

    def provenance(self, region_id: str, key: str) -> Provenance:
        value = self.manifest_entry(region_id, key).get("provenance")
        return Provenance(value) if value else Provenance.real

    def sources(self, region_id: str, key: str) -> list[SourceAttribution]:
        return [SourceAttribution(**s) for s in self.manifest_entry(region_id, key).get("sources", [])]

    def path(self, region_id: str, key: str) -> Path:
        """Parquet file, or a pre-converted ``<name>.pkl.gz`` when present.

        Pickles are produced only by our own Vercel build step from the
        checksum-verified data release (see vercel_build.py), so the
        serverless bundle can omit pyarrow. Never point this at untrusted files."""
        base = self.region_dir(region_id) / DATASETS[key].filename
        pkl = base.with_name(base.stem + ".pkl.gz")
        return pkl if pkl.exists() else base

    def has(self, region_id: str, key: str) -> bool:
        return self.path(region_id, key).exists()

    # -- loading ------------------------------------------------------------
    def load(self, region_id: str, key: str) -> pd.DataFrame | gpd.GeoDataFrame:
        spec = DATASETS[key]
        path = self.path(region_id, key)
        if not path.exists():
            raise DatasetNotAvailableError(
                f"Dataset '{key}' has not been generated for region '{region_id}'.",
                dataset=key,
                region_id=region_id,
                expected_path=str(path.relative_to(self.settings.data_dir.parent))
                if path.is_relative_to(self.settings.data_dir.parent)
                else str(path),
                hint=PIPELINE_HINT.format(region=region_id),
            )
        mtime = path.stat().st_mtime
        cache_key = (region_id, key)
        with self._lock:
            cached = self._cache.get(cache_key)
            if cached and cached[0] == mtime:
                return cached[1]
        try:
            if path.name.endswith(".pkl.gz"):
                with gzip.open(path, "rb") as fh:
                    df = pickle.load(fh)  # noqa: S301 - produced by our build from a verified release
            else:
                df = gpd.read_parquet(path) if spec.spatial else pd.read_parquet(path)
        except Exception as exc:  # pragma: no cover - defensive
            raise DatasetCorruptError(
                f"Dataset '{key}' for region '{region_id}' could not be read.", dataset=key, error=str(exc)
            ) from exc
        missing = [c for c in spec.required_columns if c not in df.columns]
        if missing:
            raise DatasetCorruptError(
                f"Dataset '{key}' is missing required columns.", dataset=key, missing_columns=missing
            )
        if spec.spatial and df.crs is not None and df.crs.to_epsg() != 4326:
            df = df.to_crs(4326)
        with self._lock:
            self._cache[cache_key] = (mtime, df)
        logger.info("Loaded %s/%s (%d rows)", region_id, key, len(df))
        return df

    def clear_cache(self) -> None:
        with self._lock:
            self._cache.clear()
