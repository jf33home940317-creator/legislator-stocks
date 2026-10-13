def names(response):
    return [item["name"] for item in response.json()["items"]]


def test_list_default_sorted_by_market_value_desc(client, sample_data):
    response = client.get("/api/v1/politicians")
    assert response.status_code == 200
    body = response.json()
    assert names(response) == ["王小明", "李小華", "陳大同"]  # 沒申報的排最後
    assert body["total"] == 3
    assert body["items"][0]["market_value"] == 10700000
    assert body["items"][0]["party"] == "中國國民黨"
    assert body["items"][2]["market_value"] is None


def test_list_sort_ascending_keeps_null_last(client, sample_data):
    response = client.get("/api/v1/politicians", params={"sort": "market_value"})
    assert names(response) == ["李小華", "王小明", "陳大同"]


def test_list_filter_by_party(client, sample_data):
    response = client.get("/api/v1/politicians", params={"party": "民主進步黨"})
    assert names(response) == ["李小華"]
    assert response.json()["items"][0]["missing_price"] is True


def test_list_pagination(client, sample_data):
    response = client.get("/api/v1/politicians", params={"limit": 1, "page": 2})
    assert names(response) == ["李小華"]
    assert response.json()["total"] == 3


def test_list_rejects_bad_params(client):
    for params in ({"limit": 101}, {"page": 0}, {"sort": "bogus"}):
        response = client.get("/api/v1/politicians", params=params)
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "validation_error"


def test_detail(client, sample_data):
    body = client.get(f"/api/v1/politicians/{sample_data['wang'].id}").json()
    assert body["district"] == "臺北市第1選區"
    assert body["declared_date"] == "2026-06-29"
    assert body["price_date"] == "2026-09-30"
    assert body["holdings"][0] == {"stock_code": "2330", "stock_name": "台積電",
                                   "owner": "本人", "shares": 10000, "close": 1050.0,
                                   "market_value": 10500000.0}
    assert len(body["holdings"]) == 2


def test_detail_without_declaration(client, sample_data):
    body = client.get(f"/api/v1/politicians/{sample_data['chen'].id}").json()
    assert body["holdings"] == []
    assert body["market_value"] is None


def test_detail_not_found(client):
    response = client.get("/api/v1/politicians/999")
    assert response.status_code == 404
    assert response.json()["error"] == {"code": "not_found", "message": "找不到這位立委"}
