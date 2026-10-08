import datetime as dt
from decimal import Decimal

import pytest
from sqlalchemy import insert
from sqlalchemy.exc import IntegrityError

from app.models import Declaration, Holding, Politician, Stock, StockPrice, Term


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


# ---------- 2-3：政治人物、任期、申報、持股 ----------

def make_declaration(**kwargs):
    """測試用的小工具：做出一份申報（連同一位政治人物）"""
    return Declaration(
        politician=Politician(name="王小明"),
        declared_date=dt.date(2026, 6, 29),
        source_url="https://example.com/a.pdf",
        **kwargs,
    )


def test_politician_with_term(session):
    p = Politician(name="王小明")
    p.terms.append(Term(role="legislator", session="第11屆", party="中國國民黨",
                        start_date=dt.date(2024, 2, 1)))
    session.add(p)
    session.commit()
    assert p.id is not None
    assert p.terms[0].politician_id == p.id
    assert p.current_term.party == "中國國民黨"


def test_current_term_is_the_latest(session):
    p = Politician(name="王小明")
    p.terms.append(Term(role="legislator", session="第11屆", party="無黨籍",
                        start_date=dt.date(2024, 2, 1)))
    p.terms.append(Term(role="legislator", session="第10屆", party="中國國民黨",
                        start_date=dt.date(2020, 2, 1)))
    session.add(p)
    session.commit()
    session.refresh(p)  # 重新從資料庫讀取，terms 才會依照 start_date 排序
    assert p.current_term.session == "第11屆"


def test_declaration_defaults_to_pending(session):
    d = make_declaration()
    session.add(d)
    session.commit()
    assert d.parse_status == "pending"


def test_invalid_parse_status_rejected(session):
    session.add(make_declaration(parse_status="bogus"))
    with pytest.raises(IntegrityError):
        session.commit()


def test_shares_must_be_positive(session):
    session.add(Stock(code="2330", name="台積電", market="TWSE"))
    d = make_declaration(parse_status="verified")
    d.holdings.append(Holding(stock_code="2330", owner="本人", shares=0))
    session.add(d)
    with pytest.raises(IntegrityError):
        session.commit()


def test_holding_requires_existing_stock(session):
    d = make_declaration(parse_status="verified")
    d.holdings.append(Holding(stock_code="9999", owner="本人", shares=100))
    session.add(d)
    with pytest.raises(IntegrityError):
        session.commit()


def test_holding_can_read_stock_name(session):
    session.add(Stock(code="2330", name="台積電", market="TWSE"))
    d = make_declaration(parse_status="verified")
    d.holdings.append(Holding(stock_code="2330", owner="配偶", shares=1000))
    session.add(d)
    session.commit()
    holding = d.holdings[0]
    assert holding.stock.name == "台積電"            # 自動 JOIN 到股票表
    assert holding.declaration.politician.name == "王小明"
