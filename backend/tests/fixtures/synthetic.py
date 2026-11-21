"""SYNTHETIC TEST FIXTURE: fabricated data for automated tests only.

Nothing here describes real places or people. GEOIDs use real state/county
codes (so code paths for Harris/Fort Bend are exercised) but invented tract
codes in the 99xxxx range, which the Census Bureau does not use for land
tracts in these counties. Every dataset written here carries
``provenance = "synthetic"`` in the manifest.
"""

from __future__ import annotations

from pathlib import Path

import geopandas as gpd
import networkx as nx
import numpy as np
import pandas as pd
from shapely.geometry import LineString, Point, box

from app.datasets import DATASETS, update_manifest_entry
from app.services.road_graph import graph_to_tables
from pipeline.processing.demographics import build_indicators

REGION_ID = "houston-sw-pilot"
SYN_SOURCE = {
    "source_id": "synthetic-fixture",
    "name": "Crisees synthetic test fixture",
    "publisher": "Crisees test suite",
    "notes": "Fabricated values for automated tests. Not real data.",
}
ORIGIN = (-95.60, 29.62)
STEP = 0.01  # degrees (~1 km)
GEOIDS = ["48201990100", "48201990200", "48157990300", "48157990400"]


def synthetic_tracts() -> gpd.GeoDataFrame:
    rows, geoms = [], []
    for i, g in enumerate(GEOIDS):
        x0 = ORIGIN[0] + (i % 2) * STEP
        y0 = ORIGIN[1] + (i // 2) * STEP
        geoms.append(box(x0, y0, x0 + STEP, y0 + STEP))
        rows.append({
            "geoid": g, "state_fips": g[:2], "county_fips": g[2:5], "tract_code": g[5:],
            "name": f"Synthetic Tract {i + 1}", "county_name": "Synthetic County",
            "land_area_m2": 1.0e6, "water_area_m2": 0.0,
            "intpt_lon": x0 + STEP / 2, "intpt_lat": y0 + STEP / 2,
            "tiger_year": 2024, "source_id": "synthetic-fixture",
        })
    return gpd.GeoDataFrame(rows, geometry=geoms, crs=4326)


def synthetic_acs_tables(geoids: list[str]) -> dict[str, pd.DataFrame]:
    """Minimal ACS-shaped tables. Tract 4 has an ACS annotation sentinel and
    tract 3 has zero households to exercise missing-value handling."""
    idx = pd.Index(geoids, name="geoid")
    pop = np.array([1000, 2000, 500, 800])

    def table(name: str, n: int, values: dict[int, np.ndarray]) -> pd.DataFrame:
        data = {}
        for i in range(1, n + 1):
            data[f"{name}_E{i:03d}"] = values.get(i, np.zeros(len(geoids), dtype=int))
            data[f"{name}_M{i:03d}"] = np.full(len(geoids), 10)
        return pd.DataFrame(data, index=idx)

    b01001_vals = {1: pop}
    for line in list(range(20, 26)) + list(range(44, 50)):
        b01001_vals[line] = np.array([10, 20, 5, 8])  # 12 cells -> 120, 240, 60, 96
    return {
        "B01003": table("B01003", 1, {1: pop}),
        "B01001": table("B01001", 49, b01001_vals),
        "B08201": table("B08201", 30, {1: np.array([400, 800, 0, 300]), 2: np.array([40, 200, 0, 30])}),
        "C17002": table("C17002", 8, {
            1: np.array([1000, 2000, 500, -666666666]),
            2: np.array([50, 100, 25, 10]), 3: np.array([50, 300, 25, 10]),
            4: np.array([10, 10, 10, 10]), 5: np.array([10, 10, 10, 10]),
        }),
        "C18108": table("C18108", 13, {
            1: pop, 3: np.array([5, 5, 5, 5]), 4: np.array([5, 5, 5, 5]), 7: np.array([20, 40, 10, 10]),
            8: np.array([10, 10, 5, 5]), 11: np.array([30, 60, 10, 20]), 12: np.array([30, 80, 15, 20]),
        }),
    }


def synthetic_graph() -> nx.MultiDiGraph:
    """3x3 grid of two-way streets plus one one-way edge."""
    G = nx.MultiDiGraph(crs="EPSG:4326")
    node = lambda r, c: 1000 + r * 10 + c  # noqa: E731
    for r in range(3):
        for c in range(3):
            G.add_node(node(r, c), x=ORIGIN[0] + c * STEP, y=ORIGIN[1] + r * STEP)
    def add(u: int, v: int, oneway: bool, cls: str, way: int) -> None:
        geom = LineString([(G.nodes[u]["x"], G.nodes[u]["y"]), (G.nodes[v]["x"], G.nodes[v]["y"])])
        attrs = dict(length=964.0, highway=cls, name=f"Synthetic St {way}", osmid=way, oneway=oneway)
        G.add_edge(u, v, reversed=False, geometry=geom, **attrs)
        if not oneway:
            G.add_edge(v, u, reversed=True, geometry=LineString(geom.coords[::-1]), **attrs)
    way = 1
    for r in range(3):
        for c in range(3):
            if c < 2:
                add(node(r, c), node(r, c + 1), oneway=(r == 2 and c == 0), cls="residential", way=way)
                way += 1
            if r < 2:
                add(node(r, c), node(r + 1, c), oneway=False, cls="primary" if c == 1 else "residential", way=way)
                way += 1
    for n in G.nodes:
        G.nodes[n]["street_count"] = len(set(G.successors(n)) | set(G.predecessors(n)))
    return G


def write_synthetic_region(processed_root: Path, skip: tuple[str, ...] = ()) -> Path:
    """Write a complete synthetic processed region; return its directory."""
    out = processed_root / REGION_ID
    out.mkdir(parents=True, exist_ok=True)

    def save(key: str, df: pd.DataFrame, extra: dict | None = None) -> None:
        if key in skip:
            return
        spec = DATASETS[key]
        path = out / spec.filename
        (gpd.GeoDataFrame(df) if spec.spatial else pd.DataFrame(df)).to_parquet(path, index=False)
        update_manifest_entry(out, REGION_ID, key, {
            "file": spec.filename, "record_count": len(df), "provenance": "synthetic",
            "provider": "synthetic", "sources": [SYN_SOURCE], "notes": ["SYNTHETIC"], "extra": extra or {},
        }, study_area_bbox=[ORIGIN[0], ORIGIN[1], ORIGIN[0] + 2 * STEP, ORIGIN[1] + 2 * STEP])

    tracts = synthetic_tracts()
    save("tracts", tracts)
    sa = gpd.GeoDataFrame({"region_id": [REGION_ID], "tract_count": [4], "area_km2": [4.0]},
                          geometry=[tracts.geometry.union_all()], crs=4326)
    save("study_area", sa)
    demo = build_indicators(synthetic_acs_tables(GEOIDS), GEOIDS, "2020-2024 ACS 5-year", "synthetic-fixture")
    save("demographics", demo)
    vuln = pd.DataFrame({
        "geoid": GEOIDS, "svi_year": 2020, "svi_geography": "US-wide percentile ranking",
        "rpl_themes": [0.1, 0.9, np.nan, 0.5], "rpl_theme4_housing_transport": [0.2, 0.95, 0.4, 0.6],
        "ep_noveh": [10.0, 25.0, np.nan, 10.0], "f_total": pd.array([0, 4, None, 1], dtype="Int64"),
        "missing_fields": [[], [], ["rpl_themes", "ep_noveh"], []], "source_id": "synthetic-fixture",
    })
    save("vulnerability", vuln)
    nodes, edges = graph_to_tables(synthetic_graph())
    save("road_nodes", nodes)
    save("road_edges", edges)
    fac = gpd.GeoDataFrame({
        "facility_id": ["syn-1", "syn-2", "syn-3"], "name": ["Synthetic Library", "Synthetic Hospital",
                                                             "Synthetic School"],
        "category": ["library", "hospital", "school"], "source_category": ["synthetic"] * 3,
        "lon": [-95.595, -95.585, -95.592], "lat": [29.625, 29.635, 29.632], "address": [None] * 3,
        "verification_status": ["mapped_unverified"] * 3, "is_designated_evacuation_shelter": [None] * 3,
        "source_id": ["synthetic-fixture"] * 3, "source_record_id": ["1", "2", "3"], "confidence": [None] * 3,
    }, geometry=[Point(-95.595, 29.625), Point(-95.585, 29.635), Point(-95.592, 29.632)], crs=4326)
    save("facilities", fac)
    hubs = gpd.GeoDataFrame({
        "hub_id": ["hub-syn-1", "hub-syn-3"], "facility_id": ["syn-1", "syn-3"],
        "name": ["Synthetic Library", "Synthetic School"], "category": ["library", "school"],
        "lon": [-95.595, -95.592], "lat": [29.625, 29.632], "candidacy_basis": ["synthetic"] * 2,
        "nearest_node_id": pd.array([1000, 1011], dtype="Int64"), "snap_distance_m": [500.0, 300.0],
        "status": ["candidate_unvalidated"] * 2,
    }, geometry=[Point(-95.595, 29.625), Point(-95.592, 29.632)], crs=4326)
    save("candidate_hubs", hubs)
    fz = gpd.GeoDataFrame({
        "hazard_id": ["fz-1", "fz-2"], "evidence_type": ["fema_regulatory"] * 2, "flood_zone": ["AE", "X"],
        "zone_subtype": [None, "0.2 PCT ANNUAL CHANCE FLOOD HAZARD"],
        "is_sfha": pd.array([True, False], dtype="boolean"), "annual_chance_category": ["1pct", "0.2pct"],
        "static_bfe_ft": [None, None], "dfirm_id": ["48157C"] * 2, "version_id": ["synthetic"] * 2,
        "source_citation": [None] * 2, "area_m2": [1.0e5, 2.0e5], "source_id": ["synthetic-fixture"] * 2,
    }, geometry=[box(-95.600, 29.620, -95.597, 29.623), box(-95.597, 29.620, -95.590, 29.623)], crs=4326)
    save("flood_hazards", fz)
    cov = gpd.GeoDataFrame({"dfirm_id": ["48157C"]}, geometry=[box(-95.60, 29.62, -95.58, 29.63)], crs=4326)
    save("flood_coverage", cov, extra={"covered_area_fraction": 0.5, "dfirm_ids": ["48157C"], "method": "synthetic"})
    return out
