"""Validation of processed datasets against the Phase 1 data contract."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

import geopandas as gpd
import pandas as pd

from app.datasets import DATASETS, read_manifest
from pipeline.context import PipelineContext

logger = logging.getLogger(__name__)


@dataclass
class ValidationResult:
    dataset: str
    ok: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    record_count: int | None = None


def _check_pct(df: pd.DataFrame, cols: list[str], errors: list[str]) -> None:
    for c in cols:
        s = df[c].dropna()
        if ((s < 0) | (s > 100)).any():
            errors.append(f"{c} outside 0-100")


def validate_dataset(ctx: PipelineContext, key: str) -> ValidationResult:
    spec = DATASETS[key]
    path = ctx.processed / spec.filename
    res = ValidationResult(dataset=key, ok=True)
    if not path.exists():
        res.ok = False
        res.errors.append(f"missing file {path.name}")
        return res
    df = gpd.read_parquet(path) if spec.spatial else pd.read_parquet(path)
    res.record_count = len(df)
    missing = [c for c in spec.required_columns if c not in df.columns]
    if missing:
        res.errors.append(f"missing columns: {missing}")
    if spec.spatial:
        if df.crs is None or df.crs.to_epsg() != 4326:
            res.errors.append(f"CRS must be EPSG:4326, got {df.crs}")
        if len(df) and (~df.geometry.is_valid).any():
            res.warnings.append(f"{int((~df.geometry.is_valid).sum())} invalid geometries")
        if len(df):
            w, s, e, n = df.total_bounds
            if not (-180 <= w <= e <= 180 and -90 <= s <= n <= 90):
                res.errors.append("bounds outside lon/lat range (axis order?)")
    if len(df) == 0 and key not in ("candidate_hubs", "flood_coverage"):
        res.warnings.append("dataset is empty")

    if key in ("tracts", "demographics", "vulnerability"):
        bad = ~df["geoid"].astype(str).str.fullmatch(r"\d{11}")
        if bad.any():
            res.errors.append(f"{int(bad.sum())} malformed GEOIDs")
        if df["geoid"].duplicated().any():
            res.errors.append("duplicate GEOIDs")
        if key == "tracts" and not df["geoid"].str[2:5].isin(ctx.region.county_fips).all():
            res.errors.append("tract outside configured counties")
    if key == "demographics":
        _check_pct(df, [c for c in df.columns if c.startswith("pct_")], res.errors)
        for num, den in [("households_no_vehicle", "households_total"),
                         ("population_65_plus", "total_population")]:
            over = (df[num] > df[den]).fillna(False)
            if over.any():
                res.warnings.append(f"{int(over.sum())} tracts with {num} > {den}")
        tracts_path = ctx.processed / DATASETS["tracts"].filename
        if tracts_path.exists():
            t = pd.read_parquet(tracts_path, columns=["geoid"])
            if set(t["geoid"]) != set(df["geoid"]):
                res.errors.append("demographics GEOIDs do not match tracts")
        nulls = int(df["total_population"].isna().sum())
        if nulls:
            res.warnings.append(f"{nulls} tracts without total population")
    if key == "vulnerability":
        for c in [c for c in df.columns if c.startswith("rpl_")]:
            s = df[c].dropna()
            if ((s < 0) | (s > 1)).any():
                res.errors.append(f"{c} outside 0-1")
    if key == "road_edges":
        nodes_path = ctx.processed / DATASETS["road_nodes"].filename
        if nodes_path.exists():
            ids = set(pd.read_parquet(nodes_path, columns=["node_id"])["node_id"])
            dangling = ~(df["u"].isin(ids) & df["v"].isin(ids))
            if dangling.any():
                res.errors.append(f"{int(dangling.sum())} edges reference missing nodes")
        if (df["length_m"] < 0).any():
            res.errors.append("negative edge length")
        if df["edge_id"].duplicated().any():
            res.errors.append("duplicate edge ids")
    if key == "road_nodes" and df["node_id"].duplicated().any():
        res.errors.append("duplicate node ids")
    if key == "facilities":
        if (df["verification_status"] == "authority_verified").any():
            res.errors.append("facility marked authority_verified without an authoritative source")
        if df["facility_id"].duplicated().any():
            res.errors.append("duplicate facility ids")
    if key == "flood_hazards" and "evidence_type" in df and (df["evidence_type"] != "fema_regulatory").any():
        res.errors.append("non-FEMA evidence types present in FEMA dataset")

    manifest = read_manifest(ctx.processed) or {}
    entry = manifest.get("datasets", {}).get(key)
    if entry is None:
        res.errors.append("no manifest entry")
    else:
        if entry.get("record_count") != len(df):
            res.errors.append(f"manifest record_count {entry.get('record_count')} != {len(df)}")
        if not entry.get("sources"):
            res.errors.append("manifest entry lacks source attribution")
        if entry.get("provenance") not in ("real", "derived", "synthetic"):
            res.errors.append("manifest entry lacks provenance")
    res.ok = not res.errors
    return res


def validate(ctx: PipelineContext) -> list[ValidationResult]:
    return [validate_dataset(ctx, key) for key in DATASETS]
