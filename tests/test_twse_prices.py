import datetime as dt
import json
from dataclasses import replace
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import func, select

from app.crawler import twse_prices
from app.crawler.base import CrawlError
from app.crawler.prices import PriceRow, save_prices
from app.models import Stock, StockPrice

FIXTURES = Path(__file__).parent / "fixtures"


def load(name):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def test_parse_fixture():
    rows, skipped = twse_prices.parse(load("twse_stock_day_all.json"))
    by_code = {r.code: r for r in rows}
    assert skipped == 1  # 00625K 沒有收盤價
    assert set(by_code) == {"2330", "2317"}
    assert by_code["2330"] == PriceRow(code="2330", name="台積電", market="TWSE",
                                       date=dt.date(2026, 9, 29), close=Decimal("2475.00"))


def test_parse_missing_field_raises():
    with pytest.raises(CrawlError, match="ClosingPrice"):
        twse_prices.parse([{"Date": "1150929", "Code": "2330", "Name": "台積電"}])


def test_parse_empty_raises():
    with pytest.raises(CrawlError):
        twse_prices.parse([])


def test_save_prices_is_upsert(session):
    rows, _ = twse_prices.parse(load("twse_stock_day_all.json"))
    assert save_prices(session, rows) == 2
    session.commit()

    tsmc = next(r for r in rows if r.code == "2330")
    save_prices(session, [replace(tsmc, close=Decimal("2500"))])
    session.commit()

    assert session.scalar(select(func.count()).select_from(StockPrice)) == 2
    assert session.get(StockPrice, ("2330", dt.date(2026, 9, 29))).close == Decimal("2500")
    assert session.get(Stock, "2317").market == "TWSE"


def test_job_uses_fetched_data(session, monkeypatch):
    monkeypatch.setattr(twse_prices, "fetch_json",
                        lambda url: load("twse_stock_day_all.json"))
    rows, message = twse_prices.job(session)
    assert rows == 2
    assert message == "跳過 1 筆沒有收盤價的資料"
