import pytest
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401  匯入後資料表才會登記到 Base.metadata
from app.db import Base, make_engine


@pytest.fixture
def engine():
    # 記憶體資料庫；StaticPool 讓所有連線共用同一個資料庫
    eng = make_engine("sqlite://", poolclass=StaticPool)
    Base.metadata.create_all(eng)   # 依照 models.py 建立所有資料表
    yield eng
    eng.dispose()


@pytest.fixture
def session_factory(engine):
    return sessionmaker(bind=engine, expire_on_commit=False)


@pytest.fixture
def session(session_factory):
    with session_factory() as s:
        yield s

@pytest.fixture
def sample_data(session):
    """
    王小明（國民黨）：最新申報 2026-06-29 verified → 2330×10000 + 2317×1000
                     市值 = 10000×1050 + 1000×200 = 10,700,000
    李小華（民進黨）：最新可用申報 2026-06-29 parsed → 2330×1000 + 6488×500（6488 沒股價）
                     市值 = 1,050,000，missing_price = True；另有 09-01 pending 申報要被忽略
    陳大同（民眾黨）：沒有申報
    """
    import datetime as dt
    from decimal import Decimal

    from app.models import Declaration, Holding, Politician, Stock, StockPrice, Term

    D = dt.date
    session.add_all([
        Stock(code="2330", name="台積電", market="TWSE"),
        Stock(code="2317", name="鴻海", market="TWSE"),
        Stock(code="6488", name="環球晶", market="TPEx"),
        StockPrice(stock_code="2330", date=D(2026, 9, 29), close=Decimal("1000")),
        StockPrice(stock_code="2330", date=D(2026, 9, 30), close=Decimal("1050")),
        StockPrice(stock_code="2317", date=D(2026, 9, 30), close=Decimal("200")),
    ])

    wang = Politician(name="王小明", terms=[Term(
        role="legislator", session="第11屆", district="臺北市第1選區",
        party="中國國民黨", start_date=D(2024, 2, 1))])
    wang.declarations = [
        Declaration(declared_date=D(2025, 11, 1), source_url="https://example.com/w1.pdf",
                    parse_status="verified",
                    holdings=[Holding(stock_code="2330", owner="本人", shares=5000)]),
        Declaration(declared_date=D(2026, 6, 29), source_url="https://example.com/w2.pdf",
                    parse_status="verified",
                    holdings=[Holding(stock_code="2330", owner="本人", shares=10000),
                              Holding(stock_code="2317", owner="配偶", shares=1000)]),
    ]

    lee = Politician(name="李小華", terms=[Term(
        role="legislator", session="第11屆", party="民主進步黨", start_date=D(2024, 2, 1))])
    lee.declarations = [
        Declaration(declared_date=D(2026, 6, 29), source_url="https://example.com/l1.pdf",
                    parse_status="parsed",
                    holdings=[Holding(stock_code="2330", owner="本人", shares=1000),
                              Holding(stock_code="6488", owner="本人", shares=500)]),
        Declaration(declared_date=D(2026, 9, 1), source_url="https://example.com/l2.pdf",
                    parse_status="pending",
                    holdings=[Holding(stock_code="2330", owner="本人", shares=99999)]),
    ]

    chen = Politician(name="陳大同", terms=[Term(
        role="legislator", session="第11屆", party="台灣民眾黨", start_date=D(2024, 2, 1))])

    session.add_all([wang, lee, chen])
    session.commit()
    return {"wang": wang, "lee": lee, "chen": chen}
