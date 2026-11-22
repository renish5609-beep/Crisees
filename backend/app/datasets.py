"""Processed-dataset contract shared by the pipeline (writer) and the API (reader).

Processed files live in ``data/processed/<region_id>/``. Spatial datasets are
GeoParquet in EPSG:4326; tabular datasets are Parquet. ``manifest.json`` in
the same folder records provenance, sources and record counts. This module
is the single source of truth for file names so Phase 2 code can rely on it.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "1.0"
MANIFEST_NAME = "manifest.json"


@dataclass(frozen=True)
class DatasetSpec:
    key: str
    filename: str
    title: str
    spatial: bool
    required_columns: tuple[str, ...]


DATASETS: dict[str, DatasetSpec] = {
    spec.key: spec
    for spec in [
        DatasetSpec("study_area", "study_area.parquet", "Study-area boundary", True, ("region_id", "geometry")),
        DatasetSpec(
            "tracts",
            "tracts.parquet",
            "Census tracts (TIGER/Line)",
            True,
            ("geoid", "state_fips", "county_fips", "tract_code", "name", "geometry"),
        ),
        DatasetSpec(
            "demographics",
            "demographics.parquet",
            "ACS 5-year demographic indicators",
            False,
            ("geoid", "total_population", "households_no_vehicle", "pct_households_no_vehicle"),
        ),
        DatasetSpec(
            "vulnerability",
            "vulnerability.parquet",
            "CDC/ATSDR Social Vulnerability Index variables",
            False,
            ("geoid", "svi_year", "rpl_themes"),
        ),
        DatasetSpec(
            "road_nodes",
            "road_nodes.parquet",
            "Drivable road network: nodes",
            True,
            ("node_id", "lon", "lat", "geometry"),
        ),
        DatasetSpec(
            "road_edges",
            "road_edges.parquet",
            "Drivable road network: edges",
            True,
            ("edge_id", "u", "v", "key", "road_class", "length_m", "oneway", "geometry"),
        ),
        DatasetSpec(
            "facilities",
            "facilities.parquet",
            "Emergency-relevant facilities (mapped, unverified)",
            True,
            ("facility_id", "category", "lon", "lat", "verification_status", "geometry"),
        ),
        DatasetSpec(
            "candidate_hubs",
            "candidate_hubs.parquet",
            "Candidate pickup hub locations (derived)",
            True,
            ("hub_id", "facility_id", "category", "lon", "lat", "geometry"),
        ),
        DatasetSpec(
            "flood_hazards",
            "flood_hazards.parquet",
            "FEMA flood hazard zones (regulatory)",
            True,
            ("hazard_id", "flood_zone", "is_sfha", "geometry"),
        ),
        DatasetSpec(
            "vehicle_access",
            "vehicle_access.parquet",
            "Zero-vehicle households by household size (ACS B08201)",
            False,
            ("geoid", "hh_no_vehicle", "hh_no_vehicle_1p", "hh_no_vehicle_4p_plus"),
        ),
        DatasetSpec(
            "edge_flood_exposure",
            "edge_flood_exposure.parquet",
            "Road-edge exposure to FEMA flood zones and data coverage (derived)",
            False,
            ("edge_id", "len_in_1pct_m", "len_in_0_2pct_m", "len_in_coverage_m"),
        ),
        DatasetSpec(
            "flood_coverage",
            "flood_coverage.parquet",
            "Extent of ingested FEMA FIRM panels",
            True,
            ("dfirm_id", "geometry"),
        ),
    ]
}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def region_processed_dir(processed_root: Path, region_id: str) -> Path:
    return processed_root / region_id


def read_manifest(region_dir: Path) -> dict[str, Any] | None:
    path = region_dir / MANIFEST_NAME
    if not path.exists():
        return None
    return json.loads(path.read_text())


def write_manifest(region_dir: Path, manifest: dict[str, Any]) -> Path:
    region_dir.mkdir(parents=True, exist_ok=True)
    path = region_dir / MANIFEST_NAME
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(manifest, indent=2, sort_keys=False, default=str))
    tmp.replace(path)
    return path


def update_manifest_entry(region_dir: Path, region_id: str, key: str, entry: dict[str, Any], **top: Any) -> None:
    manifest = read_manifest(region_dir) or {
        "region_id": region_id,
        "schema_version": SCHEMA_VERSION,
        "datasets": {},
    }
    manifest.update(top)
    manifest["generated_at"] = utc_now()
    manifest["datasets"][key] = entry
    write_manifest(region_dir, manifest)
