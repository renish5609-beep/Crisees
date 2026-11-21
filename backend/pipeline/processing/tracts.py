"""Tract selection and study-area construction."""

from __future__ import annotations

from pathlib import Path

import geopandas as gpd
from shapely.geometry import Point, box

from app.regions import RegionDefinition
from pipeline.processing.geoid import normalize_geoid_series

TRACT_COLUMNS = [
    "geoid", "state_fips", "county_fips", "tract_code", "name", "county_name", "land_area_m2",
    "water_area_m2", "intpt_lon", "intpt_lat", "tiger_year", "source_id", "geometry",
]


def load_state_tracts(zip_path: Path) -> gpd.GeoDataFrame:
    gdf = gpd.read_file(f"zip://{zip_path}")
    if gdf.crs is None:
        raise ValueError("TIGER tract file has no CRS")
    return gdf


def select_tracts(state: gpd.GeoDataFrame, region: RegionDefinition, source_id: str) -> gpd.GeoDataFrame:
    """Tracts in the region's counties whose Census internal point lies in the selection bbox."""
    gdf = state[state["COUNTYFP"].isin(region.county_fips)].copy()
    lon = gdf["INTPTLON"].astype(float)
    lat = gdf["INTPTLAT"].astype(float)
    sel = box(*region.selection_bbox)
    inside = [sel.contains(Point(x, y)) for x, y in zip(lon, lat)]
    gdf = gdf[inside].copy()
    # TIGER is NAD83 (EPSG:4269); convert to WGS84 for GeoJSON. The datum shift
    # is ~1 m in Texas, below the precision of tract boundaries.
    gdf = gdf.to_crs(4326)
    out = gpd.GeoDataFrame(
        {
            "geoid": normalize_geoid_series(gdf["GEOID"]),
            "state_fips": gdf["STATEFP"],
            "county_fips": gdf["COUNTYFP"],
            "tract_code": gdf["TRACTCE"],
            "name": gdf["NAMELSAD"],
            "county_name": gdf["COUNTYFP"].map(region.county_names),
            "land_area_m2": gdf["ALAND"].astype(float),
            "water_area_m2": gdf["AWATER"].astype(float),
            "intpt_lon": gdf["INTPTLON"].astype(float),
            "intpt_lat": gdf["INTPTLAT"].astype(float),
            "tiger_year": region.tiger_year,
            "source_id": source_id,
        },
        geometry=gdf.geometry.make_valid(),
        crs=4326,
    )
    return out.sort_values("geoid").reset_index(drop=True)[TRACT_COLUMNS]


def study_area(tracts: gpd.GeoDataFrame, region: RegionDefinition) -> gpd.GeoDataFrame:
    proj = tracts.to_crs(region.analysis_crs)
    # Small buffer/unbuffer closes slivers between adjacent tract polygons.
    geom = proj.geometry.buffer(1).union_all().buffer(-1)
    sa = gpd.GeoDataFrame(
        {
            "region_id": [region.region_id],
            "tract_count": [len(tracts)],
            "area_km2": [round(geom.area / 1e6, 3)],
        },
        geometry=[geom],
        crs=region.analysis_crs,
    ).to_crs(4326)
    return sa


def network_bbox(study: gpd.GeoDataFrame, region: RegionDefinition) -> tuple[float, float, float, float]:
    env = study.to_crs(region.analysis_crs).geometry.iloc[0].envelope.buffer(region.road_buffer_m)
    w, s, e, n = gpd.GeoSeries([env], crs=region.analysis_crs).to_crs(4326).total_bounds
    return (round(float(w), 5), round(float(s), 5), round(float(e), 5), round(float(n), 5))
