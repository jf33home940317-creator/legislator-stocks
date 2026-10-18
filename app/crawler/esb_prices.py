from typing import Any

from sqlalchemy.orm import Session

from app.crawler.base import fetch_json
from app.crawler.prices import PriceRow, parse_quotes, price_message, save_prices

URL = "https://www.tpex.org.tw/openapi/v1/tpex_esb_latest_statistics"


def parse(data: Any) -> tuple[list[PriceRow], int]:
    # 興櫃沒有收盤價，用當天最新成交價 LatestPrice 代替
    return parse_quotes(data, market="ESB", code_key="SecuritiesCompanyCode",
                        name_key="CompanyName", close_key="LatestPrice")


def job(session: Session) -> tuple[int, str | None]:
    rows, skipped = parse(fetch_json(URL))
    return save_prices(session, rows), price_message(rows, skipped)
