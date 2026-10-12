import datetime as dt
from decimal import Decimal

import pytest

from app.crawler.utils import parse_price, parse_roc_date


@pytest.mark.parametrize("text, expected", [
    ("1150929", dt.date(2026, 9, 29)),
    ("991231", dt.date(2010, 12, 31)),
    (" 1150101 ", dt.date(2026, 1, 1)),
])
def test_parse_roc_date(text, expected):
    assert parse_roc_date(text) == expected


@pytest.mark.parametrize("text", ["", "abc", "2026-09-29", "1151341"])
def test_parse_roc_date_rejects_garbage(text):
    with pytest.raises(ValueError):
        parse_roc_date(text)


@pytest.mark.parametrize("text, expected", [
    ("2475.00", Decimal("2475.00")),     # 正常價格
    ("1,234.5", Decimal("1234.5")),      # 有千分位逗號
    (" 15.51 ", Decimal("15.51")),       # 前後有空白
    ("", None),                          # 證交所：沒有成交
    (" ---", None),                      # 櫃買中心：沒有成交
    ("0", None),                         # 興櫃：沒有成交
    (None, None),                        # 欄位不存在
])
def test_parse_price(text, expected):
    assert parse_price(text) == expected