import datetime as dt
from collections.abc import Iterable
from dataclasses import dataclass, field
from decimal import Decimal

from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session, selectinload

from app.models import Declaration, Holding, StockPrice

# 只有這兩種狀態的申報可以拿來計算市值
USABLE_STATUSES = ("parsed", "verified")


@dataclass
class HoldingValue:
    stock_code: str
    stock_name: str
    owner: str
    shares: int
    close: Decimal | None
    market_value: Decimal | None


@dataclass
class Portfolio:
    declaration: Declaration | None
    holdings: list[HoldingValue] = field(default_factory=list)
    price_date: dt.date | None = None

    @property
    def market_value(self) -> Decimal | None:
        if self.declaration is None:
            return None
        return sum((h.market_value for h in self.holdings if h.market_value is not None),
                   Decimal(0))

    @property
    def missing_price(self) -> bool:
        return any(h.close is None for h in self.holdings)


def latest_declarations(session: Session,
                        politician_ids: Iterable[int] | None = None) -> dict[int, Declaration]:
    """每位立委最新一份可用的申報，key 是 politician_id。"""
    stmt = (
        select(Declaration)
        .where(Declaration.parse_status.in_(USABLE_STATUSES))
        .options(selectinload(Declaration.holdings).selectinload(Holding.stock))
        .order_by(Declaration.politician_id, Declaration.declared_date.desc(),
                  Declaration.id.desc())
    )
    if politician_ids is not None:
        stmt = stmt.where(Declaration.politician_id.in_(list(politician_ids)))
    result: dict[int, Declaration] = {}
    for declaration in session.scalars(stmt):
        result.setdefault(declaration.politician_id, declaration)  # 排序後第一份就是最新的
    return result


def latest_prices(session: Session, codes: Iterable[str]) -> dict[str, StockPrice]:
    """每檔股票最新一天的收盤價。沒有任何股價的股票不會出現在結果中。"""
    codes = list(codes)
    if not codes:
        return {}
    newest = (
        select(StockPrice.stock_code, func.max(StockPrice.date).label("max_date"))
        .where(StockPrice.stock_code.in_(codes))
        .group_by(StockPrice.stock_code)
        .subquery()
    )
    stmt = select(StockPrice).join(newest, and_(
        StockPrice.stock_code == newest.c.stock_code,
        StockPrice.date == newest.c.max_date,
    ))
    return {price.stock_code: price for price in session.scalars(stmt)}


def build_portfolio(declaration: Declaration | None,
                    prices: dict[str, StockPrice]) -> Portfolio:
    if declaration is None:
        return Portfolio(declaration=None)
    holdings: list[HoldingValue] = []
    price_dates: list[dt.date] = []
    for h in declaration.holdings:
        price = prices.get(h.stock_code)
        close = price.close if price else None
        if price:
            price_dates.append(price.date)
        holdings.append(HoldingValue(
            stock_code=h.stock_code, stock_name=h.stock.name, owner=h.owner, shares=h.shares,
            close=close, market_value=close * h.shares if close is not None else None,
        ))
    holdings.sort(key=lambda v: v.market_value or Decimal(0), reverse=True)
    return Portfolio(declaration, holdings, max(price_dates) if price_dates else None)


def portfolios(session: Session, politician_ids: list[int]) -> dict[int, Portfolio]:
    """一次算出多位立委的持股市值（避免每位各查一次的 N+1 問題）。"""
    declarations = latest_declarations(session, politician_ids)
    codes = {h.stock_code for d in declarations.values() for h in d.holdings}
    prices = latest_prices(session, codes)
    return {pid: build_portfolio(declarations.get(pid), prices) for pid in politician_ids}
