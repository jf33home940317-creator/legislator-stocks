import datetime as dt
from decimal import Decimal

import pytest
from sqlalchemy import insert
from sqlalchemy.exc import IntegrityError

from app.models import Stock, StockPrice


def test_create_stock(session):
    session.add(Stock(code="2330", name="台積電", market="TWSE"))
    session.commit()
    stock = session.get(Stock, "2330")
    assert stock.name == "台積電"


def test_market_must_be_valid(session):
    session.add(Stock(code="AAPL", name="蘋果", market="NASDAQ"))
    with pytest.raises(IntegrityError):
        session.commit()


def test_price_requires_existing_stock(session):
    session.add(StockPrice(stock_code="9999", date=dt.date(2026, 9, 30), close=Decimal("10")))
    with pytest.raises(IntegrityError):
        session.commit()


def test_one_price_per_stock_per_day(session):
    session.add(Stock(code="2330", name="台積電", market="TWSE"))
    session.commit()
    row = {"stock_code": "2330", "date": dt.date(2026, 9, 30), "close": Decimal("1050")}
    session.execute(insert(StockPrice).values(**row))
    with pytest.raises(IntegrityError):
        session.execute(insert(StockPrice).values(**row))