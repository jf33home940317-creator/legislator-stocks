from collections import defaultdict
from typing import Literal

from fastapi import APIRouter, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import SessionDep
from app.api.errors import APIError
from app.api.schemas import StockDetail, StockPage, to_float
from app.models import Declaration, Holding, Stock
from app.services.valuation import latest_declarations, latest_prices

router = APIRouter(prefix="/stocks", tags=["stocks"])

StockSort = Literal["-holders", "holders", "code"]


def _holdings_by_stock(session: Session) -> dict[str, list[tuple[Declaration, Holding]]]:
    """以每位立委最新可用的申報為準，依股票代號分組。"""
    result: dict[str, list[tuple[Declaration, Holding]]] = defaultdict(list)
    for declaration in latest_declarations(session).values():
        for holding in declaration.holdings:
            result[holding.stock_code].append((declaration, holding))
    return result


@router.get("", response_model=StockPage)
def list_stocks(
    session: SessionDep,
    sort: StockSort = "-holders",
    limit: int = Query(20, ge=1, le=100),
    page: int = Query(1, ge=1),
):
    by_stock = _holdings_by_stock(session)
    prices = latest_prices(session, by_stock)
    stocks = session.scalars(select(Stock).where(Stock.code.in_(list(by_stock)))).all()

    items = []
    for stock in stocks:
        price = prices.get(stock.code)
        items.append({
            "code": stock.code, "name": stock.name, "market": stock.market,
            "holders": len({d.politician_id for d, _ in by_stock[stock.code]}),
            "close": to_float(price.close) if price else None,
            "price_date": price.date if price else None,
        })
    items.sort(key=lambda i: i["code"])
    if sort != "code":  # Python 排序穩定，人數相同時保留代號順序
        items.sort(key=lambda i: i["holders"], reverse=sort == "-holders")

    start = (page - 1) * limit
    return {"items": items[start:start + limit], "total": len(items),
            "page": page, "limit": limit}


@router.get("/{code}", response_model=StockDetail)
def get_stock(code: str, session: SessionDep):
    stock = session.get(Stock, code)
    if stock is None:
        raise APIError(404, "not_found", "找不到這檔股票")

    price = latest_prices(session, [code]).get(code)
    holders = []
    for declaration, holding in _holdings_by_stock(session).get(code, []):
        politician = declaration.politician
        term = politician.current_term
        holders.append({
            "politician_id": politician.id, "name": politician.name,
            "party": term.party if term else None,
            "owner": holding.owner, "shares": holding.shares,
            "market_value": to_float(price.close * holding.shares) if price else None,
        })
    holders.sort(key=lambda h: h["shares"], reverse=True)

    return {"code": stock.code, "name": stock.name, "market": stock.market,
            "close": to_float(price.close) if price else None,
            "price_date": price.date if price else None, "holders": holders}
