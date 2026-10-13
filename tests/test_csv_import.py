import pytest
from sqlalchemy import select

from app.crawler.declarations.csv_import import (CsvImportError, import_holdings,
                                                 import_politicians)
from app.models import Declaration, Holding, Politician, Stock

POLITICIAN_HEADER = "id,name,name_alt,photo_url,role,session,district,party,start_date,end_date\n"
HOLDING_HEADER = "politician_id,declared_date,source_url,stock_code,owner,shares\n"


def write(tmp_path, name, text):
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


@pytest.fixture
def politician_csv(tmp_path):
    return write(tmp_path, "p.csv", POLITICIAN_HEADER +
                 "1,王小明,,,legislator,第11屆,臺北市第1選區,中國國民黨,2024-02-01,\n")


@pytest.fixture
def stocks(session):
    session.add_all([Stock(code="2330", name="台積電", market="TWSE"),
                     Stock(code="2317", name="鴻海", market="TWSE")])
    session.commit()


def test_import_politicians(session, politician_csv):
    assert import_politicians(session, politician_csv) == 1
    session.commit()
    p = session.get(Politician, 1)
    assert p.name == "王小明"
    assert p.current_term.party == "中國國民黨"
    assert p.current_term.end_date is None


def test_import_politicians_twice_updates(session, politician_csv, tmp_path):
    import_politicians(session, politician_csv)
    session.commit()
    changed = write(tmp_path, "p2.csv", POLITICIAN_HEADER +
                    "1,王小明,,,legislator,第11屆,臺北市第1選區,無黨籍,2024-02-01,\n")
    import_politicians(session, changed)
    session.commit()
    p = session.get(Politician, 1)
    assert len(p.terms) == 1              # 不會重複新增任期
    assert p.current_term.party == "無黨籍"


def test_import_politicians_rejects_bad_role(session, tmp_path):
    bad = write(tmp_path, "p.csv", POLITICIAN_HEADER +
                "1,王小明,,,mayor,第11屆,,中國國民黨,2024-02-01,\n")
    with pytest.raises(CsvImportError, match="第 2 行"):
        import_politicians(session, bad)


def test_import_holdings(session, politician_csv, stocks, tmp_path):
    import_politicians(session, politician_csv)
    csv = write(tmp_path, "h.csv", HOLDING_HEADER +
                "1,2026-06-29,https://example.com/a.pdf,2330,本人,\"10,000\"\n"
                "1,2026-06-29,https://example.com/a.pdf,2317,配偶,1000\n")
    assert import_holdings(session, csv) == 2
    session.commit()
    decl = session.scalars(select(Declaration)).one()
    assert decl.parse_status == "verified"
    assert sorted(h.shares for h in decl.holdings) == [1000, 10000]


def test_reimport_replaces_holdings(session, politician_csv, stocks, tmp_path):
    import_politicians(session, politician_csv)
    first = write(tmp_path, "h1.csv", HOLDING_HEADER +
                  "1,2026-06-29,https://example.com/a.pdf,2330,本人,10000\n"
                  "1,2026-06-29,https://example.com/a.pdf,2317,配偶,1000\n")
    import_holdings(session, first)
    session.commit()
    second = write(tmp_path, "h2.csv", HOLDING_HEADER +
                   "1,2026-06-29,https://example.com/a.pdf,2330,本人,12000\n")
    import_holdings(session, second)
    session.commit()
    assert [h.shares for h in session.scalars(select(Holding))] == [12000]
    assert len(session.scalars(select(Declaration)).all()) == 1


def test_unknown_stock_is_rejected(session, politician_csv, stocks, tmp_path):
    import_politicians(session, politician_csv)
    csv = write(tmp_path, "h.csv", HOLDING_HEADER +
                "1,2026-06-29,https://example.com/a.pdf,9999,本人,100\n")
    with pytest.raises(CsvImportError, match="9999"):
        import_holdings(session, csv)


def test_unknown_politician_is_rejected(session, stocks, tmp_path):
    csv = write(tmp_path, "h.csv", HOLDING_HEADER +
                "5,2026-06-29,https://example.com/a.pdf,2330,本人,100\n")
    with pytest.raises(CsvImportError, match="politician_id=5"):
        import_holdings(session, csv)


def test_missing_column_is_rejected(session, tmp_path):
    csv = write(tmp_path, "h.csv", "politician_id,stock_code\n1,2330\n")
    with pytest.raises(CsvImportError, match="缺少欄位"):
        import_holdings(session, csv)
