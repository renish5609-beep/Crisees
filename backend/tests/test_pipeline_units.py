"""Unit tests for pipeline processing and download safety (no network)."""

import geopandas as gpd
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import pytest
from shapely import wkb
from shapely.geometry import Point, box

from pipeline import http
from pipeline.context import PipelineContext
from pipeline.processing.facilities import derive_candidate_hubs, from_overture, dedupe
from pipeline.processing.flood import annual_chance, dfirm_county, process_coverage, process_hazards
from pipeline.processing.svi import process_svi
from pipeline.validate import validate
from tests.fixtures.synthetic import GEOIDS, synthetic_tracts


@pytest.mark.parametrize("zone,sub,cat", [("AE", None, "1pct"), ("A", "", "1pct"), ("VE", None, "1pct"),
                                          ("X", "0.2 PCT ANNUAL CHANCE FLOOD HAZARD", "0.2pct"),
                                          ("X", "AREA OF MINIMAL FLOOD HAZARD", "minimal"), ("D", None, "other")])
def test_annual_chance(zone, sub, cat):
    assert annual_chance(zone, sub) == cat


def test_dfirm_county():
    assert dfirm_county("48157C") == "48157" and dfirm_county("485464") is None and dfirm_county(None) is None


def _geojson(tmp_path, name, rows, geoms):
    p = tmp_path / name
    gpd.GeoDataFrame(rows, geometry=geoms, crs=4326).to_file(p, driver="GeoJSON")
    return p


def test_flood_hazards_clip_and_fields(tmp_path):
    p = _geojson(tmp_path, "hz.geojson",
                 [{"DFIRM_ID": "48157C", "FLD_AR_ID": "1", "FLD_ZONE": "AE", "ZONE_SUBTY": None, "SFHA_TF": "T",
                   "STATIC_BFE": -9999, "VERSION_ID": "1", "SOURCE_CIT": "x"}],
                 [box(-95.61, 29.61, -95.59, 29.63)])
    area = box(-95.60, 29.62, -95.58, 29.64)
    out = process_hazards(p, area, "EPSG:32615", "synthetic")
    assert len(out) == 1 and bool(out["is_sfha"].iloc[0]) is True
    assert out["static_bfe_ft"].iloc[0] is None  # -9999 sentinel -> null
    assert out.geometry.iloc[0].bounds == pytest.approx((-95.60, 29.62, -95.59, 29.63))
    assert out["area_m2"].iloc[0] == pytest.approx(968 * 1112, rel=0.02)


def test_flood_coverage_clipped_to_dfirm_county(tmp_path):
    tracts = synthetic_tracts()  # 2 Harris (48201) + 2 Fort Bend (48157) squares
    p = _geojson(tmp_path, "pan.geojson", [{"DFIRM_ID": "48157C"}], [box(-96, 29, -95, 30)])
    cov, stats = process_coverage(p, tracts.geometry.union_all(), "EPSG:32615", tracts)
    assert stats["covered_area_fraction"] == pytest.approx(0.5, abs=0.01)
    assert stats["dfirm_ids"] == ["48157C"]


def test_svi_processing_missing_and_matching(tmp_path):
    p = tmp_path / "svi.csv"
    pd.DataFrame({"FIPS": [48201990100, 48201990200, 48999000000], "STCNTY": ["48201"] * 3,
                  "RPL_THEMES": [0.5, -999, 0.1], "RPL_THEME4": [0.2, 0.3, 0.4], "EP_NOVEH": [12.0, -999, 1.0],
                  "F_TOTAL": [1, -999, 0]}).reindex(columns=["FIPS", "STCNTY", "RPL_THEMES", "RPL_THEME1",
                  "RPL_THEME2", "RPL_THEME3", "RPL_THEME4", "EP_POV150", "EP_UNEMP", "EP_NOHSDP", "EP_UNINSUR",
                  "EP_AGE65", "EP_AGE17", "EP_DISABL", "EP_SNGPNT", "EP_LIMENG", "EP_MINRTY", "EP_MUNIT",
                  "EP_MOBILE", "EP_CROWD", "EP_NOVEH", "EP_GROUPQ", "F_TOTAL"]).to_csv(p, index=False)
    df, stats = process_svi(p, GEOIDS, 2020, "synthetic")
    assert stats["tracts_matched"] == 2 and set(stats["unmatched_geoids"]) == set(GEOIDS[2:])
    row = df.set_index("geoid").loc["48201990200"]
    assert pd.isna(row["rpl_themes"]) and pd.isna(row["ep_noveh"]) and "rpl_themes" in row["missing_fields"]


def test_overture_facility_mapping(tmp_path):
    p = tmp_path / "places.parquet"
    def place(i, primary, conf=0.9, status="open"):
        return {"id": f"p{i}", "geometry": wkb.dumps(Point(-95.59, 29.62 + i * 1e-3)),
                "names": {"primary": f"Place {i}"}, "basic_category": primary,
                "taxonomy": {"primary": primary, "hierarchy": [primary], "alternates": []},
                "confidence": conf, "operating_status": status,
                "addresses": [{"freeform": "1 Synthetic St", "locality": "Houston", "postcode": "77000"}],
                "sources": []}
    rows = [place(1, "library"), place(2, "animal_hospital"), place(3, "hospital", conf=0.2),
            place(4, "community_center", status="permanently_closed"), place(5, "elementary_school"),
            place(6, "homeless_shelter")]
    pq.write_table(pa.Table.from_pylist(rows), p)
    gdf = from_overture(p, "synthetic")
    assert dict(zip(gdf["source_record_id"], gdf["category"])) == {"p1": "library", "p5": "school", "p6": "shelter"}
    assert (gdf["verification_status"] == "mapped_unverified").all()
    assert gdf["is_designated_evacuation_shelter"].isna().all()


def test_dedupe_and_hub_snapping():
    fac = gpd.GeoDataFrame({
        "facility_id": ["a", "b", "c", "d"], "name": ["Lib", "Lib", "School", "Far School"],
        "category": ["library", "library", "school", "school"], "lon": 0.0, "lat": 0.0,
    }, geometry=[Point(-95.6, 29.62), Point(-95.60001, 29.62001), Point(-95.59, 29.62), Point(-95.0, 29.0)], crs=4326)
    d = dedupe(fac, "EPSG:32615")
    assert d["facility_id"].tolist() == ["a", "c", "d"]
    nodes = gpd.GeoDataFrame({"node_id": [1, 2]}, geometry=[Point(-95.6, 29.6201), Point(-95.59, 29.62)], crs=4326)
    hubs = derive_candidate_hubs(d, nodes, "EPSG:32615")
    assert hubs["facility_id"].tolist() == ["a", "c"]  # far school dropped (> 300 m from network)
    assert hubs["nearest_node_id"].tolist() == [1, 2] and hubs["snap_distance_m"].iloc[1] == 0


class _FakeResp:
    def __init__(self, body: bytes, status=200):
        self.body, self.status_code = body, status
    def __enter__(self): return self
    def __exit__(self, *a): return False
    def iter_content(self, n): yield self.body
    def iter_lines(self): yield from self.body.split(b"\n")


class _FakeSession:
    def __init__(self, resp): self.resp, self.calls = resp, 0
    def get(self, *a, **k):
        self.calls += 1
        return self.resp


def test_download_rejects_error_page(tmp_path, monkeypatch):
    fake = _FakeSession(_FakeResp(b"<html><head><title>Request Rejected</title></head></html>"))
    monkeypatch.setattr(http, "session", lambda: fake)
    with pytest.raises(http.SourceUnavailableError, match="error page"):
        http.download_file("https://example.invalid/x.dat", tmp_path / "x.psv", expect_prefix=b"GEO_ID|")
    assert not (tmp_path / "x.psv").exists()


def test_download_filters_lines_and_is_idempotent(tmp_path, monkeypatch):
    body = b"GEO_ID|B01003_E001\n1400000US48201990100|10\n1400000US06037101110|5\n"
    fake = _FakeSession(_FakeResp(body))
    monkeypatch.setattr(http, "session", lambda: fake)
    dest = tmp_path / "t.psv"
    http.download_file("https://example.invalid/t", dest, line_filter=lambda l: l.startswith(b"1400000US48"),
                       expect_prefix=b"GEO_ID|")
    assert dest.read_bytes() == b"GEO_ID|B01003_E001\n1400000US48201990100|10\n"
    assert http.read_sidecar(dest)["sha256"]
    http.download_file("https://example.invalid/t", dest)  # cached: no new request
    assert fake.calls == 1


def test_download_http_error(tmp_path, monkeypatch):
    monkeypatch.setattr(http, "session", lambda: _FakeSession(_FakeResp(b"", status=503)))
    with pytest.raises(http.SourceUnavailableError, match="HTTP 503"):
        http.download_file("https://example.invalid/t", tmp_path / "t")


def test_validate_synthetic_region_passes(settings, synthetic_region):
    ctx = PipelineContext.for_region("houston-sw-pilot", settings=settings)
    results = {r.dataset: r for r in validate(ctx)}
    assert all(r.ok for r in results.values()), {k: r.errors for k, r in results.items() if not r.ok}


def test_validate_catches_dangling_edges_and_fake_verification(settings, synthetic_region):
    ctx = PipelineContext.for_region("houston-sw-pilot", settings=settings)
    nodes = gpd.read_parquet(synthetic_region / "road_nodes.parquet")
    nodes[nodes.node_id != 1000].to_parquet(synthetic_region / "road_nodes.parquet")
    fac = gpd.read_parquet(synthetic_region / "facilities.parquet")
    fac.loc[0, "verification_status"] = "authority_verified"
    fac.to_parquet(synthetic_region / "facilities.parquet")
    results = {r.dataset: r for r in validate(ctx)}
    assert any("missing nodes" in e for e in results["road_edges"].errors)
    assert any("authority_verified" in e for e in results["facilities"].errors)
