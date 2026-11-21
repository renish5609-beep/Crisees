"""FEMA flood hazard normalisation and coverage computation."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import geopandas as gpd
import pandas as pd

ONE_PCT_ZONES = {"A", "AE", "AH", "AO", "AR", "A99", "V", "VE"}


def annual_chance(zone: Any, subtype: Any) -> str:
    z = (zone or "").strip().upper()
    st = (subtype or "").upper()
    if z in ONE_PCT_ZONES:
        return "1pct"
    if z == "X" and "0.2 PCT" in st:
        return "0.2pct"
    if z == "X":
        return "minimal"
    return "other"


def _num(v: Any) -> float | None:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return None if f <= -9999 else f  # FEMA uses -9999 for 'no value'


def process_hazards(path: Path, clip_area, analysis_crs: str, source_id: str) -> gpd.GeoDataFrame:  # type: ignore[no-untyped-def]
    raw = gpd.read_file(path)
    if raw.crs is None:
        raw = raw.set_crs(4326)
    raw = raw.to_crs(4326)
    raw["geometry"] = raw.geometry.make_valid()
    clipped = gpd.clip(raw, clip_area)
    clipped = clipped[clipped.geometry.geom_type.isin(["Polygon", "MultiPolygon", "GeometryCollection"])]
    clipped["geometry"] = clipped.geometry.apply(
        lambda g: g if g.geom_type != "GeometryCollection" else
        gpd.GeoSeries([p for p in g.geoms if p.geom_type in ("Polygon", "MultiPolygon")]).union_all()
    )
    clipped = clipped[~clipped.geometry.is_empty]
    sfha = clipped.get("SFHA_TF")
    out = gpd.GeoDataFrame(
        {
            "hazard_id": [
                f"{d}-{a}-{i}" for i, (d, a) in enumerate(zip(clipped.get("DFIRM_ID"), clipped.get("FLD_AR_ID")))
            ],
            "evidence_type": "fema_regulatory",
            "flood_zone": clipped.get("FLD_ZONE"),
            "zone_subtype": clipped.get("ZONE_SUBTY"),
            "is_sfha": sfha.map({"T": True, "F": False}).astype("boolean") if sfha is not None else pd.NA,
            "annual_chance_category": [
                annual_chance(z, s) for z, s in zip(clipped.get("FLD_ZONE"), clipped.get("ZONE_SUBTY"))
            ],
            "static_bfe_ft": [_num(v) for v in clipped.get("STATIC_BFE", [None] * len(clipped))],
            "dfirm_id": clipped.get("DFIRM_ID"),
            "version_id": clipped.get("VERSION_ID"),
            "source_citation": clipped.get("SOURCE_CIT"),
            "source_id": source_id,
        },
        geometry=clipped.geometry.to_numpy(),
        crs=4326,
    )
    out["area_m2"] = out.to_crs(analysis_crs).geometry.area.round(1).to_numpy()
    return out.reset_index(drop=True)


def dfirm_county(dfirm_id: str | None) -> str | None:
    """Countywide DFIRM ids are '<state><county>C' (e.g. 48157C -> 48157)."""
    if dfirm_id and re.fullmatch(r"\d{5}C", dfirm_id):
        return dfirm_id[:5]
    return None


def process_coverage(
    panel_path: Path, study_geom, analysis_crs: str, tracts: gpd.GeoDataFrame | None = None  # type: ignore[no-untyped-def]
) -> tuple[gpd.GeoDataFrame, dict[str, Any]]:
    """Area actually described by the ingested FIRM data.

    FIRM panel squares extend beyond the county a countywide DFIRM maps, so
    for countywide DFIRMs coverage is clipped to that county's tracts.
    """
    panels = gpd.read_file(panel_path)
    if panels.crs is None:
        panels = panels.set_crs(4326)
    panels = panels.to_crs(4326)
    panels["geometry"] = panels.geometry.make_valid()
    sa = gpd.GeoSeries([study_geom], crs=4326).to_crs(analysis_crs).iloc[0]
    if panels.empty:
        cov = gpd.GeoDataFrame({"dfirm_id": []}, geometry=[], crs=4326)
        return cov, {"covered_area_fraction": 0.0, "dfirm_ids": [], "panel_count": 0}
    dissolved = panels.dissolve(by="DFIRM_ID").reset_index()[["DFIRM_ID", "geometry"]].rename(
        columns={"DFIRM_ID": "dfirm_id"}
    )
    clipped_geoms = []
    for row in dissolved.to_crs(analysis_crs).itertuples(index=False):
        geom = row.geometry.intersection(sa)
        county = dfirm_county(row.dfirm_id)
        if county and tracts is not None:
            county_area = tracts[tracts["geoid"].str[:5] == county].to_crs(analysis_crs).geometry.union_all()
            geom = geom.intersection(county_area) if county_area is not None else geom.intersection(sa).buffer(0)
        clipped_geoms.append(geom)
    dissolved = gpd.GeoDataFrame(
        {"dfirm_id": dissolved["dfirm_id"]}, geometry=clipped_geoms, crs=analysis_crs
    ).to_crs(4326)
    covered = gpd.GeoSeries(clipped_geoms, crs=analysis_crs).union_all()
    frac = round(covered.area / sa.area, 4) if sa.area else None
    return dissolved, {
        "covered_area_fraction": frac,
        "dfirm_ids": sorted(dissolved["dfirm_id"].dropna().unique().tolist()),
        "panel_count": len(panels),
        "method": "Union of FEMA FIRM panel polygons (S_FIRM_PAN) intersected with the study area and, for "
        "countywide DFIRMs, with that county's tracts; area ratio in " + analysis_crs,
    }
