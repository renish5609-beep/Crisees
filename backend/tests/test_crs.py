import geopandas as gpd
import pytest
from shapely.geometry import box

from app.regions import load_regions
from pipeline.context import PipelineContext
from pipeline.processing.tracts import network_bbox, select_tracts, study_area
from pipeline.validate import validate_dataset


def _tiger_like() -> gpd.GeoDataFrame:
    """SYNTHETIC TIGER-shaped frame in NAD83 (EPSG:4269), as TIGER/Line ships."""
    rows = []
    for i, (county, lon) in enumerate([("201", -95.55), ("157", -95.60), ("201", -94.00), ("339", -95.55)]):
        rows.append({
            "STATEFP": "48", "COUNTYFP": county, "TRACTCE": f"99{i:02d}00", "GEOID": f"48{county}99{i:02d}00",
            "NAMELSAD": f"Census Tract {i}", "ALAND": 1e6, "AWATER": 0.0,
            "INTPTLAT": "+29.6500000", "INTPTLON": f"{lon:+.7f}",
            "geometry": box(lon - 0.005, 29.645, lon + 0.005, 29.655),
        })
    return gpd.GeoDataFrame(rows, crs=4269)


def test_select_tracts_converts_to_wgs84_and_filters():
    region = load_regions()["houston-sw-pilot"]
    tracts = select_tracts(_tiger_like(), region, "synthetic")
    assert tracts.crs.to_epsg() == 4326
    # Outside-bbox (lon -94) and outside-county (339) tracts excluded.
    assert tracts["geoid"].tolist() == ["48157990100", "48201990000"]
    # GeoJSON axis order: x = longitude (negative in Houston), y = latitude.
    minx, miny, maxx, maxy = tracts.total_bounds
    assert -96 < minx < -95 and 29 < miny < 30


def test_study_area_and_network_bbox_use_metric_crs():
    region = load_regions()["houston-sw-pilot"]
    tracts = select_tracts(_tiger_like(), region, "synthetic")
    sa = study_area(tracts, region)
    assert sa.crs.to_epsg() == 4326
    assert sa["area_km2"].iloc[0] == pytest.approx(2 * 0.01 * 0.01 * 111.32 * 96.8, rel=0.05)
    w, s, e, n = network_bbox(sa, region)
    sw, ss, se, sn = sa.total_bounds
    # 1 km buffer ~ 0.009 deg latitude
    assert s < ss - 0.008 and n > sn + 0.008 and w < sw and e > se


def test_validator_rejects_non_wgs84(settings, synthetic_region):
    ctx = PipelineContext.for_region("houston-sw-pilot", settings=settings)
    path = synthetic_region / "tracts.parquet"
    gpd.read_parquet(path).to_crs(32615).to_parquet(path)
    res = validate_dataset(ctx, "tracts")
    assert not res.ok and any("EPSG:4326" in e for e in res.errors)
