"""Engine B: evacuation-assistance demand estimation.

Model (per tract t; all inputs are ACS 2020-2024 5-year estimates):

    persons_zero_vehicle_t = 1*H1 + 2*H2 + 3*H3 + p4*H4        (B08201 lines 008/014/020/026)
    demand_t               = participation * persons_zero_vehicle_t

* H1..H4 are OBSERVED counts of zero-vehicle households by size; p4 is an
  ASSUMPTION for the open-ended 4+ cell; ``participation`` is a HYPOTHETICAL
  share of those residents who would request assisted evacuation.
* Older-adult, disability and poverty indicators are NOT added to demand:
  the same people can appear in several tables, so summing would double
  count. They enter only as *priority weights* (rates, never counts).
* If the size cells are missing but the zero-vehicle total exists, the
  tract's mean household size (population / households) is used and the
  tract is flagged. If the total is missing, demand is null (not 0) and the
  tract is excluded from optimisation with a flag.

Spatial allocation: each tract's demand is split across sub-tract *origin
cells* (grid cells of ``origin_cell_m`` intersected with the tract) in
proportion to residential street length, a documented housing proxy. A cell's
origin is the residential-length-weighted centroid snapped to the walk network.
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import product

import geopandas as gpd
import numpy as np
import pandas as pd

from app.engine.network import RoadNetwork
from app.engine.params import DemandParams, EquityWeights

SIZE_COLS = ["hh_no_vehicle_1p", "hh_no_vehicle_2p", "hh_no_vehicle_3p", "hh_no_vehicle_4p_plus"]


@dataclass
class Origins:
    """Sub-tract origin units (rows) with their share of tract demand."""

    table: pd.DataFrame  # origin_id, geoid, share, x, y, lon, lat, walk_node, drive_node, snap_m, method

    def __len__(self) -> int:
        return len(self.table)


def build_origins(tracts: gpd.GeoDataFrame, net: RoadNetwork, analysis_crs: str, cell_m: float) -> Origins:
    import pyproj

    # One representative direction per physical residential segment.
    res = net.residential.copy()
    first_of_segment = ~pd.Series(net.segment_id).duplicated().to_numpy()
    mask = res & first_of_segment
    mx = (net.x[net.u[mask]] + net.x[net.v[mask]]) / 2
    my = (net.y[net.u[mask]] + net.y[net.v[mask]]) / 2
    w = net.length_m[mask]
    pts = gpd.GeoDataFrame({"w": w, "mx": mx, "my": my}, geometry=gpd.points_from_xy(mx, my), crs=analysis_crs)
    tp = tracts[["geoid", "geometry"]].to_crs(analysis_crs)
    joined = gpd.sjoin(pts, tp, how="inner", predicate="within")
    joined["cell"] = (np.floor(joined["mx"] / cell_m).astype(int).astype(str) + "_"
                      + np.floor(joined["my"] / cell_m).astype(int).astype(str))
    joined["wx"], joined["wy"] = joined["mx"] * joined["w"], joined["my"] * joined["w"]
    g = joined.groupby(["geoid", "cell"]).agg(w=("w", "sum"), wx=("wx", "sum"), wy=("wy", "sum")).reset_index()
    g["x"], g["y"] = g["wx"] / g["w"], g["wy"] / g["w"]
    g["share"] = g["w"] / g.groupby("geoid")["w"].transform("sum")
    g["method"] = "residential_street_length"
    # Tracts with no residential streets: a single origin at the Census internal point.
    missing = sorted(set(tracts["geoid"]) - set(g["geoid"]))
    if missing:
        t = tracts.set_index("geoid").loc[missing]
        to_proj = pyproj.Transformer.from_crs(4326, analysis_crs, always_xy=True)
        ix, iy = to_proj.transform(t["intpt_lon"].to_numpy(), t["intpt_lat"].to_numpy())
        g = pd.concat([g, pd.DataFrame({"geoid": missing, "cell": "internal_point", "w": 0.0, "x": ix, "y": iy,
                                        "share": 1.0, "method": "census_internal_point"})], ignore_index=True)
    g = g.sort_values(["geoid", "cell"]).reset_index(drop=True)
    g["origin_id"] = g["geoid"] + ":" + g["cell"]
    g["walk_node"], g["snap_m"] = net.nearest_node(g["x"].to_numpy(), g["y"].to_numpy(), walkable_only=True)
    g["drive_node"], _ = net.nearest_node(g["x"].to_numpy(), g["y"].to_numpy())
    to_wgs = pyproj.Transformer.from_crs(analysis_crs, 4326, always_xy=True)
    g["lon"], g["lat"] = to_wgs.transform(g["x"].to_numpy(), g["y"].to_numpy())
    cols = ["origin_id", "geoid", "share", "x", "y", "lon", "lat", "walk_node", "drive_node", "snap_m", "method"]
    return Origins(g[cols])


def tract_demand(vehicle_access: pd.DataFrame, demographics: pd.DataFrame, params: DemandParams) -> pd.DataFrame:
    """Per-tract demand with observed inputs, assumptions and flags kept apart."""
    va = vehicle_access.set_index("geoid")
    demo = demographics.set_index("geoid").reindex(va.index)
    sizes = va[SIZE_COLS].astype("Float64")
    persons = (sizes["hh_no_vehicle_1p"] + 2 * sizes["hh_no_vehicle_2p"] + 3 * sizes["hh_no_vehicle_3p"]
               + params.persons_in_4plus_households * sizes["hh_no_vehicle_4p_plus"])
    method = pd.Series("household_size_cells", index=va.index, dtype=object)
    avg_hh = demo["total_population"].astype("Float64") / demo["households_total"].astype("Float64").replace(0, pd.NA)
    fallback = persons.isna() & va["hh_no_vehicle"].notna()
    persons[fallback] = va.loc[fallback, "hh_no_vehicle"].astype("Float64") * avg_hh[fallback]
    method[fallback] = "total_x_mean_household_size"
    method[persons.isna()] = "unavailable"
    out = pd.DataFrame(index=va.index)
    out["households_no_vehicle"] = va["hh_no_vehicle"]
    for c in SIZE_COLS:
        out[c] = va[c]
    out["persons_zero_vehicle_est"] = persons.astype(float).round(1)
    out["demand_est"] = (persons.astype(float) * params.participation_rate).round(2)
    out["demand_method"] = method
    out["total_population"] = demo["total_population"]
    return out.reset_index()


def _pct_rank(s: pd.Series) -> tuple[pd.Series, pd.Series]:
    """Within-region percentile rank in [0, 1]; missing -> neutral 0.5 (flagged)."""
    r = s.rank(method="average", pct=True)
    n = s.notna().sum()
    if n > 1:  # rescale so min -> 0, max -> 1
        r = (r * n - 1) / (n - 1)
    missing = s.isna()
    return r.fillna(0.5).clip(0, 1), missing


def priority_weights(demographics: pd.DataFrame, demand: pd.DataFrame, weights: EquityWeights) -> pd.DataFrame:
    demo = demographics.set_index("geoid").reindex(demand["geoid"])
    out = pd.DataFrame({"geoid": demand["geoid"].to_numpy()})
    raw = np.ones(len(out))
    flags = [[] for _ in range(len(out))]
    terms = {"poverty": ("pct_below_poverty", weights.beta_poverty),
             "disability": ("pct_with_disability", weights.beta_disability),
             "age65": ("pct_65_plus", weights.beta_age65)}
    for name, (col, beta) in terms.items():
        rank, missing = _pct_rank(demo[col].astype(float))
        out[f"rank_{name}"] = rank.round(4).to_numpy()
        if weights.mode == "equity" and beta > 0:
            raw = raw + beta * rank.to_numpy()
            for i in np.flatnonzero(missing.to_numpy()):
                flags[i].append(f"{col}_missing_rank_set_to_0.5")
    if weights.mode == "equal":
        raw = np.ones(len(out))
    d = demand["demand_est"].fillna(0).to_numpy()
    mean = (d * raw).sum() / d.sum() if d.sum() > 0 else raw.mean()
    out["weight_raw"] = raw.round(4)
    out["weight"] = (raw / mean).round(6)
    out["weight_flags"] = flags
    return out


def sensitivity(vehicle_access: pd.DataFrame, demographics: pd.DataFrame,
                participation: list[float], p4: list[float]) -> list[dict]:
    rows = []
    for pr, size in product(participation, p4):
        d = tract_demand(vehicle_access, demographics, DemandParams(participation_rate=pr,
                                                                    persons_in_4plus_households=size))
        rows.append({"participation_rate": pr, "persons_in_4plus_households": size,
                     "total_demand": round(float(d["demand_est"].sum()), 1),
                     "max_tract_demand": round(float(d["demand_est"].max()), 1)})
    return rows
