"""Pipeline orchestration: download -> process -> validate, per region.

Each step is idempotent: downloads are skipped when a file and its
``.source.json`` provenance sidecar already exist (use ``force`` to refresh),
and processing overwrites outputs atomically.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Callable

import geopandas as gpd
import pandas as pd

from app.datasets import DATASETS, update_manifest_entry, utc_now
from pipeline.context import PipelineContext
from pipeline.http import SourceUnavailableError, read_sidecar
from pipeline.processing import demographics as demo_proc
from pipeline.processing import facilities as fac_proc
from pipeline.processing import flood as flood_proc
from pipeline.processing import roads as road_proc
from pipeline.processing import svi as svi_proc
from pipeline.processing import tracts as tract_proc
from pipeline.sources import acs, catalog, fema, svi, tiger
from pipeline.sources import facilities as fac_src
from pipeline.sources import roads as road_src
from app.services.road_graph import graph_to_tables

logger = logging.getLogger("crisees.pipeline")

STEPS = ("tracts", "acs", "svi", "flood", "roads", "facilities")


class StepReport(dict):
    pass


def _study_area_from_raw(ctx: PipelineContext) -> tuple[gpd.GeoDataFrame, gpd.GeoDataFrame]:
    src = catalog.tiger_tracts(ctx.region.tiger_year, ctx.region.state_fips)
    state = tract_proc.load_state_tracts(tiger.tract_zip_path(ctx))
    tracts = tract_proc.select_tracts(state, ctx.region, src["source_id"])
    return tracts, tract_proc.study_area(tracts, ctx.region)


# --------------------------------------------------------------------- download
def download(ctx: PipelineContext, steps: tuple[str, ...] = STEPS, road_provider: str = "auto",
             facility_provider: str = "auto") -> list[StepReport]:
    reports: list[StepReport] = []

    def run(name: str, fn: Callable[[], Any]) -> None:
        if name not in steps:
            return
        try:
            result = fn()
            reports.append(StepReport(step=name, status="ok", result=str(result)))
        except SourceUnavailableError as exc:
            logger.error("download %s failed: %s", name, exc)
            reports.append(StepReport(step=name, status="failed", error=str(exc)))

    # Tract boundaries are needed to derive the network bbox for other sources.
    run("tracts", lambda: tiger.download_tracts(ctx))
    bbox = None
    if tiger.tract_zip_path(ctx).exists():
        _, sa = _study_area_from_raw(ctx)
        bbox = tract_proc.network_bbox(sa, ctx.region)
        logger.info("network bbox (study area + %.0f m): %s", ctx.region.road_buffer_m, bbox)
    run("acs", lambda: acs.download_acs(ctx))
    run("svi", lambda: svi.download_svi(ctx))
    if bbox is None:
        for name in ("flood", "roads", "facilities"):
            if name in steps:
                reports.append(StepReport(step=name, status="skipped", error="tract boundaries unavailable"))
        return reports
    run("flood", lambda: fema.download_flood(ctx, bbox))
    run("roads", lambda: road_src.download_roads(ctx, bbox, road_provider))
    run("facilities", lambda: fac_src.download_facilities(ctx, bbox, facility_provider))
    return reports


# --------------------------------------------------------------------- process
def _write(ctx: PipelineContext, key: str, df: pd.DataFrame, *, provenance: str, provider: str | None,
           sources: list[dict], notes: list[str] | None = None, extra: dict | None = None, **top: Any) -> Path:
    spec = DATASETS[key]
    ctx.processed.mkdir(parents=True, exist_ok=True)
    path = ctx.processed / spec.filename
    tmp = path.with_name(path.name + ".part")
    if spec.spatial:
        gpd.GeoDataFrame(df).to_parquet(tmp, index=False)
    else:
        pd.DataFrame(df).to_parquet(tmp, index=False)
    tmp.replace(path)
    entry = {
        "file": spec.filename,
        "title": spec.title,
        "record_count": int(len(df)),
        "provenance": provenance,
        "provider": provider,
        "crs": "EPSG:4326" if spec.spatial else None,
        "sources": sources,
        "notes": notes or [],
        "generated_at": utc_now(),
        "extra": extra or {},
    }
    update_manifest_entry(ctx.processed, ctx.region.region_id, key, entry, **top)
    logger.info("wrote %s (%d records)", spec.filename, len(df))
    return path


def _src_with_retrieval(path: Path) -> dict:
    meta = read_sidecar(path)
    src = dict(meta.get("source", {}))
    if meta.get("retrieved_at"):
        src["retrieved_at"] = meta["retrieved_at"]
    return src


def process(ctx: PipelineContext, steps: tuple[str, ...] = STEPS) -> list[StepReport]:
    reports: list[StepReport] = []
    r = ctx.region

    def run(name: str, fn: Callable[[], Any]) -> None:
        if name not in steps:
            return
        try:
            reports.append(StepReport(step=name, status="ok", result=fn()))
        except FileNotFoundError as exc:
            logger.error("process %s skipped, raw data missing: %s", name, exc)
            reports.append(StepReport(step=name, status="missing_raw", error=str(exc)))

    state: dict[str, Any] = {}

    def do_tracts() -> dict:
        zp = tiger.tract_zip_path(ctx)
        if not zp.exists():
            raise FileNotFoundError(zp)
        tracts, sa = _study_area_from_raw(ctx)
        src = _src_with_retrieval(zp)
        bounds = [round(float(b), 6) for b in sa.total_bounds]
        _write(ctx, "tracts", tracts, provenance="real", provider="tiger", sources=[src],
               notes=[r.selection_rule], study_area_bbox=bounds)
        _write(ctx, "study_area", sa, provenance="derived", provider="crisees", sources=[src],
               notes=["Union of selected tracts (1 m buffer/unbuffer to close slivers)."])
        state["tracts"], state["study_area"] = tracts, sa
        return {"tracts": len(tracts), "counties": tracts["county_fips"].value_counts().to_dict(),
                "area_km2": float(sa["area_km2"].iloc[0])}

    def tracts_df() -> gpd.GeoDataFrame:
        if "tracts" not in state:
            state["tracts"] = gpd.read_parquet(ctx.processed / DATASETS["tracts"].filename)
            state["study_area"] = gpd.read_parquet(ctx.processed / DATASETS["study_area"].filename)
        return state["tracts"]

    def do_acs() -> dict:
        tables = {}
        pov_table = acs.poverty_table(ctx)
        if pov_table is None:
            raise FileNotFoundError(acs.table_path(ctx, acs.POVERTY_TABLES[0]))
        for t in [t for t in acs.ACS_TABLES if t not in acs.POVERTY_TABLES] + [pov_table]:
            p = acs.table_path(ctx, t)
            if not p.exists():
                raise FileNotFoundError(p)
            tables[t] = demo_proc.read_table(p)
        geoids = tracts_df()["geoid"].tolist()
        meta = read_sidecar(acs.table_path(ctx, "B01003"))
        src = dict(meta.get("source", catalog.acs5(r.acs_year, "summary_file")))
        src["retrieved_at"] = meta.get("retrieved_at")
        vintage = f"{r.acs_year - 4}-{r.acs_year} ACS 5-year"
        df = demo_proc.build_indicators(tables, geoids, vintage, src["source_id"])
        src["notes"] = "Tables: " + ", ".join(sorted(tables)) + f"; retrieved via {meta.get('method')}."
        notes = ["Counts are ACS estimates (real); percentages and summed counts are derived.",
                 "None/NaN means unavailable; never imputed as 0."]
        if pov_table != "C17002":
            notes.append(f"Poverty from {pov_table} because C17002 could not be retrieved; "
                         "population_below_150pct_poverty is unavailable (null).")
        _write(ctx, "demographics", df, provenance="derived", provider=meta.get("method"), sources=[src],
               notes=notes, extra={"tables": sorted(tables), "poverty_table": pov_table})
        return {"tracts": len(df), "with_missing": int(df["missing_fields"].map(len).gt(0).sum())}

    def do_svi() -> dict:
        p = svi.svi_path(ctx)
        if not p.exists():
            raise FileNotFoundError(p)
        meta = read_sidecar(p)
        src = _src_with_retrieval(p)
        df, stats = svi_proc.process_svi(p, tracts_df()["geoid"].tolist(), int(meta.get("svi_year", 0)),
                                         src.get("source_id", "svi"))
        notes = [f"Matched {stats['tracts_matched']}/{stats['tracts_requested']} tracts by GEOID."]
        if meta.get("svi_year") != r.acs_year:
            notes.append(f"SVI {meta.get('svi_year')} is based on an earlier ACS vintage than the ACS "
                         f"{r.acs_year} indicators; do not combine without accounting for the time gap.")
        _write(ctx, "vulnerability", df, provenance="real", provider=meta.get("provider"), sources=[src],
               notes=notes, extra=stats)
        return stats

    def do_flood() -> dict:
        hz, pn = fema.hazard_path(ctx), fema.panel_path(ctx)
        if not hz.exists():
            raise FileNotFoundError(hz)
        tracts_df()
        sa_geom = state["study_area"].geometry.iloc[0]
        meta = read_sidecar(hz)
        src = _src_with_retrieval(hz)
        hazards = flood_proc.process_hazards(hz, sa_geom, r.analysis_crs, src.get("source_id", "fema"))
        cov_gdf, cov = flood_proc.process_coverage(pn, sa_geom, r.analysis_crs, state["tracts"])
        notes = ["FEMA regulatory flood zones; not observed or real-time flooding."]
        if cov.get("covered_area_fraction") is not None and cov["covered_area_fraction"] < 0.99:
            notes.append(f"Only {cov['covered_area_fraction']:.0%} of the study area is covered by ingested "
                         f"FIRM panels ({', '.join(cov['dfirm_ids'])}). Uncovered areas have NO DATA.")
        _write(ctx, "flood_hazards", hazards, provenance="real", provider=meta.get("provider"), sources=[src],
               notes=notes, extra=cov)
        _write(ctx, "flood_coverage", cov_gdf, provenance="derived", provider=meta.get("provider"),
               sources=[src], notes=[cov.get("method", "")], extra=cov)
        return {"polygons": len(hazards), **{k: v for k, v in cov.items() if k != "method"}}

    def do_roads() -> dict:
        found = road_src.raw_roads(ctx)
        if not found:
            raise FileNotFoundError(ctx.region_raw / "roads")
        provider, path = found
        meta = read_sidecar(path)
        src = _src_with_retrieval(path)
        stats: dict[str, Any] = {"provider": provider}
        if provider == "osmnx":
            G = road_proc.osmnx_to_graph(path)
        else:
            G, s = road_proc.overture_to_graph(path, r.analysis_crs)
            stats.update(s)
        G, s = road_proc.finalize_graph(G)
        stats.update(s)
        nodes, edges = graph_to_tables(G)
        stats.update(road_proc.clip_edges_check(edges))
        notes = [f"Network bbox (study area bounds + {r.road_buffer_m:.0f} m): {meta.get('bbox')}",
                 "Largest weakly connected component retained (OSMnx retain_all=False convention)."]
        if provider == "overture":
            notes.append("Built from Overture transportation segments (OpenStreetMap-derived) because the "
                         "Overpass API was unreachable; osm_way_ids reference the source OSM ways.")
            notes.append("Edge lengths are planar lengths in " + r.analysis_crs + ".")
        common = dict(provenance="real", provider=provider, sources=[src], notes=notes, extra=stats)
        _write(ctx, "road_nodes", nodes, **common)
        _write(ctx, "road_edges", edges, **common)
        state["nodes"] = nodes
        return stats

    def do_facilities() -> dict:
        found = fac_src.raw_facilities(ctx)
        if not found:
            raise FileNotFoundError(ctx.region_raw / "facilities")
        provider, path = found
        src = _src_with_retrieval(path)
        tracts_df()
        gdf = fac_proc.from_osm(path, src["source_id"]) if provider == "osm" else fac_proc.from_overture(
            path, src["source_id"])
        gdf = fac_proc.clip_to(gdf, state["study_area"].geometry.iloc[0])
        gdf = fac_proc.dedupe(gdf, r.analysis_crs)
        notes = ["Mapped facilities from open data. NONE are verified designated evacuation shelters.",
                 "'shelter' = mapped social/homeless shelter, not an emergency-management designation."]
        if provider == "overture":
            notes.append(f"Overture places with confidence >= {fac_proc.OVERTURE_MIN_CONFIDENCE} and not "
                         "permanently closed.")
        _write(ctx, "facilities", gdf, provenance="real", provider=provider, sources=[src], notes=notes,
               extra={"by_category": gdf["category"].value_counts().to_dict()})
        nodes = state.get("nodes")
        if nodes is None and (ctx.processed / DATASETS["road_nodes"].filename).exists():
            nodes = gpd.read_parquet(ctx.processed / DATASETS["road_nodes"].filename)
        hubs = fac_proc.derive_candidate_hubs(gdf, nodes, r.analysis_crs)
        _write(ctx, "candidate_hubs", hubs, provenance="derived", provider="crisees", sources=[src],
               notes=["Candidates = community centres, libraries, schools, municipal buildings within "
                      f"{fac_proc.HUB_MAX_SNAP_M:.0f} m of the drivable network. Planning hypotheses only."])
        return {"facilities": len(gdf), "candidate_hubs": len(hubs)}

    run("tracts", do_tracts)
    run("acs", do_acs)
    run("svi", do_svi)
    run("flood", do_flood)
    run("roads", do_roads)
    run("facilities", do_facilities)
    return reports
