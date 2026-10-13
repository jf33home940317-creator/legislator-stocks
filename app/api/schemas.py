import datetime as dt
from decimal import Decimal

from pydantic import BaseModel


def to_float(value: Decimal | None) -> float | None:
    return float(value) if value is not None else None


class Meta(BaseModel):
    latest_price_date: dt.date | None
    latest_declared_date: dt.date | None
    last_crawled_at: dt.datetime | None
    politician_count: int


class HoldingOut(BaseModel):
    stock_code: str
    stock_name: str
    owner: str
    shares: int
    close: float | None
    market_value: float | None


class PoliticianSummary(BaseModel):
    id: int
    name: str
    name_alt: str | None
    photo_url: str | None
    party: str | None
    session: str | None
    declared_date: dt.date | None
    market_value: float | None
    missing_price: bool


class PoliticianDetail(PoliticianSummary):
    district: str | None
    price_date: dt.date | None
    holdings: list[HoldingOut]


class PoliticianPage(BaseModel):
    items: list[PoliticianSummary]
    total: int
    page: int
    limit: int


class StockSummary(BaseModel):
    code: str
    name: str
    market: str
    holders: int
    close: float | None
    price_date: dt.date | None


class StockPage(BaseModel):
    items: list[StockSummary]
    total: int
    page: int
    limit: int


class StockHolder(BaseModel):
    politician_id: int
    name: str
    party: str | None
    owner: str
    shares: int
    market_value: float | None


class StockDetail(BaseModel):
    code: str
    name: str
    market: str
    close: float | None
    price_date: dt.date | None
    holders: list[StockHolder]
