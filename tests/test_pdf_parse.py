import datetime as dt
from decimal import Decimal

import pytest

from app.crawler.base import CrawlError
from app.crawler.declarations.pdf_parse import (
    Header, owner_of, parse_header, parse_stock_tables, stated_stock_total, totals_match)

# 以下文字都是從真實 PDF 用 pdf_text() 抽出來的格式（人名已改）

HEADER = """公 職 人 員 財 產 申 報 表
申報人姓名 王小明 服 務 機 關 職 稱
申 報 日 114年11月01日 申 報 類 別 定期申報
稱 謂 姓 名 稱 謂 姓 名
配偶 陳美麗 未成年子女 王○安
未成年子女 王○樂
（二）不動產
"""


# ---------- parse_header ----------

def test_parse_header():
    h = parse_header(HEADER)
    assert h.declarant == "王小明"
    assert h.declared_date == dt.date(2025, 11, 1)
    assert h.spouses == ("陳美麗",)
    assert h.children == ("王○安", "王○樂")      # 同一行兩組、下一行再一組都要抓到


def test_parse_header_skips_noise_before_year():
    noisy = HEADER.replace("114年", "1★114年")      # 真實 PDF（李柏毅）出現過
    assert parse_header(noisy).declared_date == dt.date(2025, 11, 1)


def test_parse_header_rejects_unknown_format():
    with pytest.raises(CrawlError):
        parse_header("完全不是申報表的文字")


# ---------- stated_stock_total ----------

def test_stated_stock_total():
    assert stated_stock_total("（八）有價證券\n1.股票（總價額：新臺幣186,000元）\n名 稱") == 186000
    assert stated_stock_total("1.股票（總價額：新臺幣 元）\n本欄空白") is None


def test_stated_stock_total_rejects_missing_section():
    with pytest.raises(CrawlError):
        stated_stock_total(HEADER)


# ---------- parse_stock_tables ----------
# 以下表格都照 pdfplumber extract_tables() 從真實 PDF 抽出來的樣子（人名已改）

STOCK_HEAD = ["名 稱", "所 有 人", "股 數", "票 面 價 額", "外 幣 幣 別", "新臺幣總額或折合新臺幣\n總 額"]
DEPOSIT_TAIL = [["某銀行", "活期存款", "新臺幣", "王小明", "", "12,732"]]          # 存款表跨頁的接續
BOND_HEAD = [["名 稱", "代 碼", "所 有 人", "買 賣 機 構", "單 位 數", "票 面 價 額", "外 幣 幣 別", "總 額"],
             ["某債券", "X1", "王小明", "某券商", "100", "10", "", "1,000"]]


def test_parse_stock_tables_basic_trust_and_wrapped_name():
    tables = [DEPOSIT_TAIL, [
        STOCK_HEAD,
        ["高興昌", "陳美麗", "16,000", "10", "", "160,000"],
        ["台泥「交付臺灣銀行信託」", "王 小明", "2,000", "10", "", "20,000"],     # 信託：所有人中間有空格
        ["華南金「交付臺灣銀行信\n託」", "王小明", "600", "10", "", "6,000"],     # 名稱換行
    ], BOND_HEAD]
    lines = parse_stock_tables(tables)
    assert [(s.name, s.holder, s.shares, s.total) for s in lines] == [
        ("高興昌", "陳美麗", 16000, 160000),
        ("台泥「交付臺灣銀行信託」", "王小明", 2000, 20000),
        ("華南金「交付臺灣銀行信託」", "王小明", 600, 6000),
    ]
    assert lines[0].raw == "高興昌 陳美麗 16,000 10 160,000"


def test_parse_stock_tables_continues_across_pages():
    tables = [[STOCK_HEAD, ["高興昌", "陳美麗", "16,000", "10", "", "160,000"]],
              [["大成鋼", "王小明", "2,000", "10", "", "20,000"]],                  # 下一頁：沒有標題列
              BOND_HEAD]
    assert [s.name for s in parse_stock_tables(tables)] == ["高興昌", "大成鋼"]


def test_parse_stock_tables_header_at_page_bottom():
    tables = [[STOCK_HEAD],                                                        # 標題列在頁底
              [["", "", "", "", "", "總 額"],                                      # 標題第二行被擠到下一頁
               ["大成鋼", "王小明", "2,000", "10", "", "20,000"]]]
    assert [s.name for s in parse_stock_tables(tables)] == ["大成鋼"]


def test_parse_stock_tables_ignores_deposit_continuation_before_stocks():
    assert parse_stock_tables([DEPOSIT_TAIL, [STOCK_HEAD, ["本欄空白", "", "", "", "", ""]]]) == []


def test_parse_stock_tables_foreign_stock():
    [line] = parse_stock_tables([[STOCK_HEAD, ["蘋果電腦", "王小明", "500", "270.37", "美元", "4,142,744.33"]]])
    assert line.currency == "美元" and line.total == Decimal("4142744.33")


def test_totals_match():
    lines = parse_stock_tables([[STOCK_HEAD, ["高興昌", "陳美麗", "16,000", "10", "", "160,000"],
                                 ["蘋果電腦", "王小明", "1", "270.37", "美元", "8,285.49"]]])
    assert totals_match(lines, 168285)          # 外幣小數四捨五入，差在列數以內算對
    assert not totals_match(lines, 200000)      # 差太多 → 有漏抓
    assert totals_match([], None)


# ---------- owner_of ----------

def test_owner_of():
    h = Header("王小明", dt.date(2025, 11, 1), spouses=("陳美麗",), children=("王○安",))
    assert owner_of("王小明", h) == "本人"
    assert owner_of("陳美麗", h) == "配偶"
    assert owner_of("王○安", h) == "未成年子女"     # 股票表也打碼
    assert owner_of("王志安", h) == "未成年子女"     # 股票表沒打碼，○ 以外的字相同
    assert owner_of("李大同", h) is None            # 對不上 → 交給人工
