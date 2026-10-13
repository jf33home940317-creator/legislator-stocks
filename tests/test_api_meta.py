def test_meta_on_empty_database(client):
    response = client.get("/api/v1/meta")
    assert response.status_code == 200
    assert response.json() == {"latest_price_date": None, "latest_declared_date": None,
                               "last_crawled_at": None, "politician_count": 0}


def test_meta_with_data(client, sample_data):
    body = client.get("/api/v1/meta").json()
    assert body["latest_price_date"] == "2026-09-30"
    assert body["latest_declared_date"] == "2026-06-29"  # pending 的 09-01 不算
    assert body["politician_count"] == 3


def test_unknown_route_uses_error_format(client):
    response = client.get("/api/v1/nope")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_cors_allows_localhost(client):
    response = client.get("/api/v1/meta", headers={"Origin": "http://localhost:5173"})
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"
