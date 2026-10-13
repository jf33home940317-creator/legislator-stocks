from app.models import Stock


def test_list_sorted_by_holders(client, sample_data):
    body = client.get("/api/v1/stocks").json()
    assert [(i["code"], i["holders"]) for i in body["items"]] == [
        ("2330", 2), ("2317", 1), ("6488", 1)]  # 同人數依代號排序
    assert body["items"][0]["close"] == 1050.0
    assert body["items"][2]["close"] is None


def test_list_excludes_stocks_nobody_holds(client, session, sample_data):
    session.add(Stock(code="1101", name="台泥", market="TWSE"))
    session.commit()
    codes = [i["code"] for i in client.get("/api/v1/stocks").json()["items"]]
    assert "1101" not in codes


def test_detail_lists_holders(client, sample_data):
    body = client.get("/api/v1/stocks/2330").json()
    assert body["name"] == "台積電"
    assert body["price_date"] == "2026-09-30"
    assert [(h["name"], h["shares"]) for h in body["holders"]] == [
        ("王小明", 10000), ("李小華", 1000)]  # pending 的 99999 股不算
    assert body["holders"][0]["market_value"] == 10500000.0
    assert body["holders"][0]["party"] == "中國國民黨"


def test_detail_without_price(client, sample_data):
    body = client.get("/api/v1/stocks/6488").json()
    assert body["close"] is None
    assert body["holders"][0]["market_value"] is None


def test_detail_not_found(client):
    response = client.get("/api/v1/stocks/9999")
    assert response.status_code == 404
    assert response.json()["error"]["message"] == "找不到這檔股票"
