from typing import Any

from sqlalchemy.orm import Session

from app.crawler.base import fetch_json
from app.crawler.prices import PriceRow, parse_quotes, save_prices, skipped_message

URL = "https://www.tpex.org.tw/openapi/v1/tpex_mainboard_daily_close_quotes"


def parse(data: Any) -> tuple[list[PriceRow], int]:
    return parse_quotes(data, market="TPEx", code_key="SecuritiesCompanyCode",
                        name_key="CompanyName", close_key="Close")


def job(session: Session) -> tuple[int, str | None]:
    rows, skipped = parse(fetch_json(URL))
    return save_prices(session, rows), skipped_message(skipped)
