from typing import Any

from sqlalchemy.orm import Session

from app.crawler.base import fetch_json
from app.crawler.prices import PriceRow, parse_quotes, save_prices, skipped_message

URL = "https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL"


def parse(data: Any) -> tuple[list[PriceRow], int]:
    return parse_quotes(data, market="TWSE", code_key="Code", name_key="Name",
                        close_key="ClosingPrice")


def job(session: Session) -> tuple[int, str | None]:
    rows, skipped = parse(fetch_json(URL))
    return save_prices(session, rows), skipped_message(skipped)
