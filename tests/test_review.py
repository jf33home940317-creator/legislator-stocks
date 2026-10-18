import datetime as dt
from decimal import Decimal

import pytest

from app.crawler.declarations.csv_import import CsvImportError, import_holdings
from app.crawler.declarations.pdf_parse import Header, StockLine
from app.crawler.declarations.review import (
    chinese_name, match_code, name_index, normalize_name, review_rows, write_review_csv)
from app.models import Politician, Stock

HEADER = Header("王小明", dt.date(2025, 11, 1), spouses=("陳美麗",), children=())
CODES = {"台積電": "2330", "鴻海": "2317"}
ALIASES = {"台積": "2330"}


def line(name: str, holder: str, shares: int, currency: str = "") -> StockLine:
    return StockLine(name=name, holder=holder, shares=shares, total=Decimal(shares * 10), currency=currency,
                     raw=f"{name} {holder} {shares} 10 {shares * 10}")


def rows_for(stocks: list[StockLine], stated: int | None = None) -> list[dict]:
    if stated is None:
        stated = sum(s.total for s in stocks)
    return review_rows(1, HEADER, stocks, stated, "https://example.com/x", CODES, ALIASES)


def test_chinese_name():
    assert chinese_name("伍麗華Saidhai‧Tahovecahe") == "伍麗華"
    assert chinese_name("王小明") == "王小明"


def test_match_code_exact_then_alias_never_guess():
    assert match_code("台積電", CODES, ALIASES) == "2330"
    assert match_code("台積", CODES, ALIASES) == "2330"      # 別名表
    assert match_code("鴻", CODES, ALIASES) is None          # 不做模糊比對


def test_normalize_name():
    assert normalize_name("台泥「交付臺灣銀行信託」") == "台泥"
    assert normalize_name("臺化") == "台化"
    assert normalize_name("國巨＊") == "國巨"


def test_match_code_uses_normalized_name():
    assert match_code("鴻海「交付臺灣銀行信託」", CODES, ALIASES) == "2317"


def test_name_index_normalizes_db_names_but_skips_collisions():
    index = name_index([("2327", "國巨*"), ("1111", "甲*"), ("2222", "甲＊"), ("2330", "台積電")])
    assert index["國巨"] == "2327"          # PDF 寫「國巨＊」或「國巨「交付臺灣銀行信託」」都對得到
    assert "甲" not in index                # 兩檔正規化後撞名 → 不加
    assert index["台積電"] == "2330"


def test_review_rows_flags_foreign_stock():
    [row] = rows_for([line("台積電", "王小明", 1, currency="美元")])   # 就算名字對得上台股也不要
    assert row["stock_code"] == "" and "外國股票" in row["problem"]


def test_review_rows_clean():
    rows = rows_for([line("台積電", "王小明", 1000), line("鴻海", "陳美麗", 500)])
    assert [(r["stock_code"], r["owner"], r["shares"], r["problem"]) for r in rows] == [
        ("2330", "本人", 1000, ""), ("2317", "配偶", 500, "")]
    assert rows[0]["declared_date"] == "2025-11-01"


def test_review_rows_flags_problems():
    rows = rows_for([line("勝華", "王小明", 1000), line("鴻海", "李大同", 500)])
    assert rows[0]["stock_code"] == "" and "股票代號" in rows[0]["problem"]
    assert rows[1]["owner"] == "" and "李大同" in rows[1]["problem"]


def test_review_rows_flags_total_mismatch():
    rows = rows_for([line("台積電", "王小明", 1000)], stated=999999)
    assert "總價額" in rows[0]["problem"]


# ---------- 審核 CSV 要能直接給 import_holdings 用 ----------

@pytest.fixture
def db(session):
    session.add_all([Politician(id=1, name="王小明"),
                     Stock(code="2330", name="台積電", market="TWSE"),
                     Stock(code="2317", name="鴻海", market="TWSE")])
    session.flush()
    return session


def test_clean_review_csv_imports(db, tmp_path):
    path = tmp_path / "review.csv"
    write_review_csv(rows_for([line("台積電", "王小明", 1000), line("鴻海", "陳美麗", 500)]), path)
    assert import_holdings(db, path) == 2


def test_review_csv_with_problem_is_rejected(db, tmp_path):
    path = tmp_path / "review.csv"
    write_review_csv(rows_for([line("台積電", "王小明", 1000), line("勝華", "王小明", 1)]), path)
    with pytest.raises(CsvImportError):     # 沒處理完的問題，資料就進不去
        import_holdings(db, path)


# ---------- build_review：一位失敗不影響其他人 ----------

def test_build_review_isolates_failures(session, tmp_path, monkeypatch):
    import contextlib

    from app.crawler.base import CrawlError
    from app.crawler.declarations import review

    def fake_review_one(client, session, name, codes, aliases, delay):
        if name == "壞掉":
            raise CrawlError("PDF 格式可能改了")
        return rows_for([line("台積電", "王小明", 1000)]), "1 檔"

    monkeypatch.setattr(review, "review_one", fake_review_one)
    monkeypatch.setattr(review.cy_pdf, "make_client", contextlib.nullcontext)   # 不連網

    count, summary = review.build_review(session, ["甲", "壞掉", "乙"], tmp_path / "out.csv")
    assert count == 2                     # 甲、乙都有寫進去
    assert "失敗 1 位" in summary and "壞掉" in summary


def test_review_one_strips_invisible_whitespace(session):
    from app.crawler.declarations.review import review_one
    # 找不到人會丟 CrawlError；名字帶 \r 時應該先被 strip，才會往下走到查詢（這裡用假 client 擋住）
    session.add(Politician(id=7, name="王小明"))
    session.flush()

    class StopHere(Exception):
        pass

    class FakeClient:
        def post(self, *args, **kwargs):
            raise StopHere

    with pytest.raises(StopHere):        # 有走到查詢 = 有找到立委
        review_one(FakeClient(), session, "王小明\r", {}, {}, delay=0)
