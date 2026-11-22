R = "/api/v1/regions/houston-sw-pilot"


def test_regions_list(client):
    r = client.get("/api/v1/regions")
    assert r.status_code == 200
    region = r.json()[0]
    assert region["region_id"] == "houston-sw-pilot"
    states = {d["dataset"]: d["state"] for d in region["datasets"]}
    assert set(states.values()) == {"available"}
    assert all(d["provenance"] == "synthetic" for d in region["datasets"])


def test_tracts_geojson_and_pagination(client):
    r = client.get(f"{R}/tracts", params={"limit": 3})
    body = r.json()
    assert r.status_code == 200 and body["type"] == "FeatureCollection"
    assert body["page"] == {"total": 4, "limit": 3, "offset": 0, "returned": 3, "next_offset": 3}
    f = body["features"][0]
    assert f["geometry"]["type"] == "Polygon"
    lon, lat = f["geometry"]["coordinates"][0][0]
    assert -96 < lon < -95 and 29 < lat < 30  # [lon, lat] order
    assert body["provenance"] == "synthetic"
    r2 = client.get(f"{R}/tracts", params={"limit": 3, "offset": 3, "include_geometry": False})
    assert r2.json()["page"]["next_offset"] is None and r2.json()["features"][0]["geometry"] is None


def test_tracts_county_filter_and_simplify(client):
    r = client.get(f"{R}/tracts", params={"county_fips": "157", "simplify_m": 10})
    assert [f["id"][:5] for f in r.json()["features"]] == ["48157", "48157"]


def test_page_size_bounded_by_server_max(client):
    r = client.get(f"{R}/roads", params={"limit": 100000})
    assert r.status_code == 422 or r.json()["page"]["limit"] == 100
    assert client.get(f"{R}/roads", params={"limit": 0}).status_code == 422


def test_demographics_include_vulnerability_and_nulls(client):
    body = client.get(f"{R}/demographics").json()
    assert body["page"]["total"] == 4
    recs = {r["demographics"]["geoid"]: r for r in body["records"]}
    assert recs["48201990100"]["demographics"]["pct_households_no_vehicle"] == 10.0
    assert recs["48157990300"]["demographics"]["pct_households_no_vehicle"] is None
    assert recs["48157990300"]["vulnerability"]["rpl_themes"] is None
    assert recs["48201990200"]["vulnerability"]["rpl_themes"] == 0.9
    one = client.get(f"{R}/demographics", params={"geoid": "48201990200", "include_vulnerability": False}).json()
    assert len(one["records"]) == 1 and one["records"][0]["vulnerability"] is None


def test_demographics_rejects_bad_geoid(client):
    r = client.get(f"{R}/demographics", params={"geoid": "123"})
    assert r.status_code == 422 and r.json()["error"]["code"] == "validation_error"


def test_roads_edges_nodes_and_filters(client):
    edges = client.get(f"{R}/roads").json()
    assert edges["page"]["total"] == 23
    e = edges["features"][0]
    assert e["geometry"]["type"] == "LineString" and {"u", "v", "key", "oneway", "length_m"} <= e["properties"].keys()
    nodes = client.get(f"{R}/roads", params={"layer": "nodes"}).json()
    assert nodes["page"]["total"] == 9 and nodes["features"][0]["geometry"]["type"] == "Point"
    prim = client.get(f"{R}/roads", params={"road_class": "primary"}).json()
    assert {f["properties"]["road_class"] for f in prim["features"]} == {"primary"}
    bb = client.get(f"{R}/roads", params={"bbox": "-95.601,29.619,-95.595,29.621"}).json()
    assert 0 < bb["page"]["total"] < 23


def test_roads_bad_bbox(client):
    for bad in ["1,2,3", "a,b,c,d", "10,10,0,0"]:
        r = client.get(f"{R}/roads", params={"bbox": bad})
        assert r.status_code == 400 and r.json()["error"]["code"] == "bad_request"


def test_facilities_and_hubs(client):
    body = client.get(f"{R}/facilities").json()
    assert body["page"]["total"] == 4
    assert all(f["properties"]["verification_status"] == "mapped_unverified" for f in body["features"])
    lib = client.get(f"{R}/facilities", params={"category": "library"}).json()
    assert [f["properties"]["name"] for f in lib["features"]] == ["Synthetic Library"]
    assert client.get(f"{R}/facilities", params={"category": "spaceport"}).status_code == 400
    hubs = client.get(f"{R}/candidate-hubs").json()
    assert hubs["page"]["total"] == 2 and hubs["features"][0]["properties"]["status"] == "candidate_unvalidated"


def test_flood_hazards(client):
    body = client.get(f"{R}/flood-hazards").json()
    assert body["page"]["total"] == 2
    assert body["coverage"]["covered_area_fraction"] == 0.5
    assert "not observed" in body["disclaimer"]
    sfha = client.get(f"{R}/flood-hazards", params={"sfha_only": True}).json()
    assert [f["properties"]["flood_zone"] for f in sfha["features"]] == ["AE"]
    assert sfha["features"][0]["properties"]["evidence_type"] == "fema_regulatory"


def test_summary_computed_from_data(client):
    s = client.get(f"{R}/summary").json()
    assert s["population"]["total_population"] == 4300
    assert s["population"]["households_no_vehicle"] == 270
    # Consistent ratio: tract 3 (zero households) contributes to neither side.
    assert s["population"]["pct_households_no_vehicle"] == round(100 * 270 / 1500, 2)
    assert s["roads"]["node_count"] == 9 and s["roads"]["weakly_connected_components"] == 1
    assert s["facilities"]["authority_verified_shelters"] == 0
    assert s["flood"]["polygon_count"] == 2 and s["flood"]["tracts_intersecting_sfha"] == 1
    assert s["unavailable_datasets"] == []


def test_missing_datasets_return_503(empty_client):
    for path in ["tracts", "demographics", "roads", "facilities", "flood-hazards", "candidate-hubs"]:
        r = empty_client.get(f"{R}/{path}")
        assert r.status_code == 503, path
        err = r.json()["error"]
        assert err["code"] == "dataset_not_available" and "process_data.py" in err["details"]["hint"]


def test_summary_with_no_data_lists_unavailable(empty_client):
    s = empty_client.get(f"{R}/summary").json()
    assert s["population"] is None and s["roads"] is None and len(s["unavailable_datasets"]) == 4


def test_datasets_status_when_missing(empty_client):
    states = {d["dataset"]: d["state"] for d in empty_client.get(f"{R}/datasets").json()}
    assert set(states.values()) == {"missing"}


def test_unknown_region_404(client):
    r = client.get("/api/v1/regions/atlantis/tracts")
    assert r.status_code == 404 and r.json()["error"]["code"] == "region_not_found"
    assert client.get("/api/v1/regions/Bad_ID/tracts").status_code == 422


def test_partial_data_demographics_without_svi(settings, repo, data_dir):
    from tests.conftest import _client
    from tests.fixtures.synthetic import write_synthetic_region

    write_synthetic_region(data_dir / "processed", skip=("vulnerability",))
    c = _client(settings, repo)
    body = c.get(f"{R}/demographics").json()
    assert body["records"][0]["vulnerability"] is None
