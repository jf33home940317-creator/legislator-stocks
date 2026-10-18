import datetime as dt

import pytest

from app.crawler.base import CrawlError
from app.crawler.declarations.pdf_parse import Header, owner_of, parse_header, parse_stocks

# 以下文字都是從真實 PDF 用 pdf_text() 抽出來的格式（人名已改）

HEADER = """公 職 人 員 財 產 申 報 表
申報人姓名 王小明 服 務 機 關 職 稱
申 報 日 114年11月01日 申 報 類 別 定期申報
稱 謂 姓 名 稱 謂 姓 名
配偶 陳美麗 未成年子女 王○安
未成年子女 王○樂
（二）不動產
"""

STOCKS = """（八）有價證券（總價額：新臺幣 186,000元）
1.股票（總價額：新臺幣186,000元）
新臺幣總額或折合新臺幣
名 稱 所 有 人 股 數 票 面 價 額 外 幣 幣 別
總 額
高興昌 陳美麗 16,000 10 160,000
大成鋼 王小明 2,000 10 20,000
監察院公報 ............. 廉 政 專 刊 第 299 期 90
名 稱 所 有 人 股 數 票 面 價 額 外 幣 幣 別 新臺幣總額或折合新臺幣
亞光 王○安 600 10 6,000
2.債券（總價額：新臺幣 元）
某債券 王小明 100 10 1,000
"""

EMPTY = """1.股票（總價額：新臺幣 元）
新臺幣總額或折合新臺幣
名 稱 所 有 人 股 數 票 面 價 額 外 幣 幣 別
總 額
本欄空白
2.債券（總價額：新臺幣 元）
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


# ---------- parse_stocks ----------

def test_parse_stocks_skips_page_footer_and_repeated_header():
    lines, stated = parse_stocks(STOCKS)
    assert [(s.name, s.holder, s.shares) for s in lines] == [
        ("高興昌", "陳美麗", 16000), ("大成鋼", "王小明", 2000), ("亞光", "王○安", 600)]
    assert stated == 186000
    assert sum(s.total for s in lines) == stated    # 每列加總要等於表上總價額
    assert lines[0].raw == "高興昌 陳美麗 16,000 10 160,000"


def test_parse_stocks_stops_before_bonds():
    names = [s.name for s in parse_stocks(STOCKS)[0]]
    assert "某債券" not in names


def test_parse_stocks_empty_section():
    assert parse_stocks(EMPTY) == ([], None)


def test_parse_stocks_rejects_missing_section():
    with pytest.raises(CrawlError):
        parse_stocks(HEADER)


# ---------- owner_of ----------

def test_owner_of():
    h = Header("王小明", dt.date(2025, 11, 1), spouses=("陳美麗",), children=("王○安",))
    assert owner_of("王小明", h) == "本人"
    assert owner_of("陳美麗", h) == "配偶"
    assert owner_of("王○安", h) == "未成年子女"     # 股票表也打碼
    assert owner_of("王志安", h) == "未成年子女"     # 股票表沒打碼，○ 以外的字相同
    assert owner_of("李大同", h) is None            # 對不上 → 交給人工
