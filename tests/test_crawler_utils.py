import datetime as dt

import pytest

from app.crawler.utils import parse_roc_date


@pytest.mark.parametrize("text, expected", [
    ("1150929", dt.date(2026, 9, 29)),
    ("991231", dt.date(2010, 12, 31)),                       # 民國 99 年 12 月 31 日
    (" 1150101 ", dt.date(2026, 1, 1)),                    # 前後有空白，民國 115 年 1 月 1 日
])
def test_parse_roc_date(text, expected):
    assert parse_roc_date(text) == expected


@pytest.mark.parametrize("text", ["", "abc", "2026-09-29", "1151341"])
def test_parse_roc_date_rejects_garbage(text):
    with pytest.raises(ValueError):
        parse_roc_date(text)