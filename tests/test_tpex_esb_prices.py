import datetime as dt
import json
from decimal import Decimal
from pathlib import Path

from app.crawler import esb_prices, tpex_prices
from app.crawler.prices import PriceRow

FIXTURES = Path(__file__).parent / "fixtures"


def load(name):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


# ---------- 上櫃 TPEx ----------

def test_tpex_parse():
    rows, skipped = tpex_prices.parse(load("tpex_daily_close.json"))
    assert skipped == 1  # 橘子 Close 是 " ---"
    assert rows == [PriceRow(code="6488", name="環球晶", market="TPEx",
                             date=dt.date(2026, 9, 30), close=Decimal("400.50"))]


def test_tpex_job(session, monkeypatch):
    monkeypatch.setattr(tpex_prices, "fetch_json", lambda url: load("tpex_daily_close.json"))
    assert tpex_prices.job(session) == (1, "跳過 1 筆沒有收盤價的資料")


# ---------- 興櫃 ESB ----------

def test_esb_parse():
    rows, skipped = esb_prices.parse(load("tpex_esb_latest.json"))
    assert skipped == 1  # LatestPrice 是 "0" 代表沒成交
    assert rows == [PriceRow(code="1260", name="富味鄉", market="ESB",
                             date=dt.date(2026, 9, 30), close=Decimal("31.95"))]


def test_esb_job(session, monkeypatch):
    monkeypatch.setattr(esb_prices, "fetch_json", lambda url: load("tpex_esb_latest.json"))
    assert esb_prices.job(session) == (1, "跳過 1 筆沒有收盤價的資料")
