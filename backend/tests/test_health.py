def test_health_ok(client):
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["regions_configured"] >= 1
    assert body["regions_with_processed_data"] == 1
    assert body["data_dir_exists"] is True


def test_health_without_data(empty_client):
    r = empty_client.get("/health")
    assert r.status_code == 200
    assert r.json()["regions_with_processed_data"] == 0


def test_cors_allows_local_frontend(client):
    r = client.options(
        "/health", headers={"Origin": "http://localhost:3000", "Access-Control-Request-Method": "GET"}
    )
    assert r.headers.get("access-control-allow-origin") == "http://localhost:3000"
