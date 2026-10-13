import datetime as dt
from decimal import Decimal

from app.services.valuation import latest_declarations, latest_prices, portfolios


def test_latest_declarations_skip_pending(session, sample_data):
    decls = latest_declarations(session)
    assert decls[sample_data["wang"].id].declared_date == dt.date(2026, 6, 29)
    assert decls[sample_data["lee"].id].declared_date == dt.date(2026, 6, 29)
    assert sample_data["chen"].id not in decls


def test_latest_prices_pick_newest_date(session, sample_data):
    prices = latest_prices(session, {"2330", "6488"})
    assert prices["2330"].close == Decimal("1050")
    assert prices["2330"].date == dt.date(2026, 9, 30)
    assert "6488" not in prices


def test_portfolio_values(session, sample_data):
    ids = [p.id for p in sample_data.values()]
    result = portfolios(session, ids)

    wang = result[sample_data["wang"].id]
    assert wang.market_value == Decimal("10700000")
    assert wang.price_date == dt.date(2026, 9, 30)
    assert wang.missing_price is False
    assert [h.stock_code for h in wang.holdings] == ["2330", "2317"]  # 市值由大到小

    lee = result[sample_data["lee"].id]
    assert lee.market_value == Decimal("1050000")
    assert lee.missing_price is True
    assert next(h for h in lee.holdings if h.stock_code == "6488").market_value is None

    chen = result[sample_data["chen"].id]
    assert chen.declaration is None
    assert chen.market_value is None
    assert chen.holdings == []
