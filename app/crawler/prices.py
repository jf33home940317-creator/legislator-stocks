import datetime as dt
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session

from app.crawler.base import CrawlError
from app.crawler.utils import parse_price, parse_roc_date
from app.models import Stock, StockPrice


@dataclass(frozen=True)
class PriceRow:
    """整理好的一筆股價"""
    code: str
    name: str
    market: str
    date: dt.date
    close: Decimal


def parse_quotes(data: Any, *, market: str, code_key: str, name_key: str,
                 close_key: str, date_key: str = "Date") -> tuple[list[PriceRow], int]:
    """把行情 JSON 轉成 PriceRow。回傳（資料列, 跳過筆數）。"""
    # 檢查 1：回應必須是「不是空的 list」，而且裡面是 dict
    if not isinstance(data, list) or not data or not isinstance(data[0], dict):
        raise CrawlError("回應是空的，或不是物件清單")
    # 檢查 2：第一筆資料要有我們需要的所有欄位，沒有就代表 API 格式改了
    missing = {date_key, code_key, name_key, close_key} - set(data[0])
    if missing:
        raise CrawlError(f"回應缺少欄位 {sorted(missing)}，API 格式可能改了")

    rows: dict[str, PriceRow] = {}
    skipped = 0
    for item in data:                                    # ① 逐筆處理 API 回傳的每一筆
        code = (item.get(code_key) or "").strip()
        close = parse_price(item.get(close_key))         # ② 你 Task 4 寫的價格轉換
        if not code or close is None:
            skipped += 1
            continue                                     # ③ 沒代號或沒成交 → 跳過這筆
        try:
            day = parse_roc_date(item.get(date_key) or "")   # ④ 你 Task 4 寫的民國日期轉換
        except ValueError:                               # ⑤ parse_roc_date 格式錯誤時丟的錯誤
            skipped += 1
            continue
        name = (item.get(name_key) or "").strip()
        rows[code] = PriceRow(code, name, market, day, close)
    return list(rows.values()), skipped                  # ⑥ 回傳資料列 + 跳過的筆數

def _dialect_insert(session):
    """SQLite 與 PostgreSQL 的 upsert 寫法相同，只是從不同模組匯入。"""
    if session.get_bind().dialect.name == "postgresql":
        from sqlalchemy.dialects.postgresql import insert
    else:
        from sqlalchemy.dialects.sqlite import insert
    return insert


def save_prices(session, rows: list[PriceRow]) -> int:
    """把 PriceRow 寫入資料庫：股票 upsert、股價 upsert（已存在就更新收盤價）。"""
    if not rows:
        return 0
    insert = _dialect_insert(session)

    # 股票：已存在就更新名稱與市場，不存在就新增
    stock_stmt = insert(Stock)
    stock_stmt = stock_stmt.on_conflict_do_update(
        index_elements=["code"],
        set_={"name": stock_stmt.excluded["name"], "market": stock_stmt.excluded["market"]},
    )
    session.execute(stock_stmt, [{"code": r.code, "name": r.name, "market": r.market}
                                 for r in rows])

    # 股價：同一檔同一天已存在就更新收盤價（所以爬蟲重跑不會重複）
    price_stmt = insert(StockPrice)
    price_stmt = price_stmt.on_conflict_do_update(
        index_elements=["stock_code", "date"],
        set_={"close": price_stmt.excluded["close"]},
    )
    session.execute(price_stmt, [{"stock_code": r.code, "date": r.date, "close": r.close}
                                 for r in rows])
    return len(rows)


def skipped_message(skipped: int) -> str | None:
    return f"跳過 {skipped} 筆沒有收盤價的資料" if skipped else None
