"""Derived inputs for Phase 2: vehicle-access detail and road flood exposure."""

from __future__ import annotations

import logging

import geopandas as gpd
import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# ACS B08201 "Household size by vehicles available": no-vehicle cells by size.
B08201_NO_VEHICLE = {"hh_no_vehicle": 2, "hh_no_vehicle_1p": 8, "hh_no_vehicle_2p": 14, "hh_no_vehicle_3p": 20,
                     "hh_no_vehicle_4p_plus": 26}


def vehicle_access(b08201: pd.DataFrame, geoids: list[str], source_id: str) -> pd.DataFrame:
    """Zero-vehicle households by size for each tract. ACS sentinels -> null."""
    idx = pd.Index(sorted(geoids), name="geoid")
    t = b08201.reindex(idx)
    out = pd.DataFrame(index=idx)
    for name, line in B08201_NO_VEHICLE.items():
        est = t[f"B08201_E{line:03d}"].where(lambda s: s >= 0)
        moe = t[f"B08201_M{line:03d}"].where(lambda s: s >= 0)
        out[name] = est.round().astype("Int64")
        out[f"{name}_moe"] = moe
    parts = out[["hh_no_vehicle_1p", "hh_no_vehicle_2p", "hh_no_vehicle_3p", "hh_no_vehicle_4p_plus"]]
    total = out["hh_no_vehicle"]
    out["size_cells_consistent"] = (parts.sum(axis=1, min_count=4) == total).astype("boolean")
    out.loc[parts.isna().any(axis=1) | total.isna(), "size_cells_consistent"] = pd.NA
    out["source_id"] = source_id
    return out.reset_index()


def edge_flood_exposure(
    edges: gpd.GeoDataFrame,
    hazards: gpd.GeoDataFrame,
    coverage: gpd.GeoDataFrame,
    analysis_crs: str,
) -> pd.DataFrame:
    """Length of each directed edge inside 1%-annual-chance zones, 0.2% zones
    and inside the area covered by ingested FEMA data (metres, analysis CRS).

    Exposure is *regulatory* (FEMA), not observed flooding. Length outside
    ``coverage`` has unknown hazard status.
    """
    e = edges[["edge_id", "geometry"]].to_crs(analysis_crs)
    hz = hazards.to_crs(analysis_crs)
    out = pd.DataFrame({"edge_id": e["edge_id"].to_numpy(), "length_m": e.geometry.length.to_numpy()})

    def inside_length(polys: gpd.GeoSeries) -> np.ndarray:
        lengths = np.zeros(len(e))
        if len(polys) == 0:
            return lengths
        union = polys.union_all()
        # Spatial index prefilter, then exact intersection only for candidates.
        hit = e.sindex.query(union, predicate="intersects")
        if len(hit):
            geoms = e.geometry.iloc[hit]
            lengths[hit] = geoms.intersection(union).length.to_numpy()
        return lengths

    one_pct = hz[hz["annual_chance_category"] == "1pct"].geometry
    point_two = hz[hz["annual_chance_category"] == "0.2pct"].geometry
    out["len_in_1pct_m"] = inside_length(one_pct).round(2)
    out["len_in_0_2pct_m"] = inside_length(point_two).round(2)
    cov = coverage.to_crs(analysis_crs).geometry if len(coverage) else gpd.GeoSeries([], crs=analysis_crs)
    out["len_in_coverage_m"] = inside_length(cov).round(2)
    out["length_m"] = out["length_m"].round(2)
    # Distance (m) from each edge to the nearest 1%-annual-chance polygon, capped
    # at 1000 m (NaN beyond). Used by hypothetical "overbank" closure rules.
    out["dist_to_1pct_m"] = np.nan
    if len(one_pct):
        polys = gpd.GeoDataFrame(geometry=one_pct.explode(index_parts=False).reset_index(drop=True), crs=analysis_crs)
        near = gpd.sjoin_nearest(e[["geometry"]], polys, how="left", max_distance=1000, distance_col="_d")
        near = near[~near.index.duplicated()]
        out["dist_to_1pct_m"] = near["_d"].reindex(e.index).round(1).to_numpy()
    return out
