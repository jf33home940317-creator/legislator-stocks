from typing import Literal

from fastapi import APIRouter, Query
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.api.deps import SessionDep
from app.api.errors import APIError
from app.api.schemas import PoliticianDetail, PoliticianPage, to_float
from app.models import Politician
from app.services.valuation import Portfolio, portfolios

router = APIRouter(prefix="/politicians", tags=["politicians"])

PoliticianSort = Literal["-market_value", "market_value", "name", "-name"]


def _summary(p: Politician, pf: Portfolio) -> dict:
    term = p.current_term
    return {
        "id": p.id, "name": p.name, "name_alt": p.name_alt, "photo_url": p.photo_url,
        "party": term.party if term else None,
        "session": term.session if term else None,
        "declared_date": pf.declaration.declared_date if pf.declaration else None,
        "market_value": to_float(pf.market_value),
        "missing_price": pf.missing_price,
    }


def _sort(items: list[dict], sort: str) -> list[dict]:
    """依欄位排序；該欄位是 null 的一律排最後（不論升冪降冪）。"""
    key = sort.lstrip("-")
    present = [i for i in items if i[key] is not None]
    absent = [i for i in items if i[key] is None]
    present.sort(key=lambda i: i[key], reverse=sort.startswith("-"))
    return present + absent


@router.get("", response_model=PoliticianPage)
def list_politicians(
    session: SessionDep,
    party: str | None = None,
    sort: PoliticianSort = "-market_value",
    limit: int = Query(20, ge=1, le=100),
    page: int = Query(1, ge=1),
):
    politicians = session.scalars(
        select(Politician).options(selectinload(Politician.terms)).order_by(Politician.id)
    ).all()
    if party is not None:
        politicians = [p for p in politicians
                       if p.current_term and p.current_term.party == party]

    pfs = portfolios(session, [p.id for p in politicians])
    items = _sort([_summary(p, pfs[p.id]) for p in politicians], sort)
    start = (page - 1) * limit
    return {"items": items[start:start + limit], "total": len(items),
            "page": page, "limit": limit}


@router.get("/{politician_id}", response_model=PoliticianDetail)
def get_politician(politician_id: int, session: SessionDep):
    politician = session.get(Politician, politician_id)
    if politician is None:
        raise APIError(404, "not_found", "找不到這位立委")

    pf = portfolios(session, [politician.id])[politician.id]
    term = politician.current_term
    return {
        **_summary(politician, pf),
        "district": term.district if term else None,
        "price_date": pf.price_date,
        "holdings": [
            {"stock_code": h.stock_code, "stock_name": h.stock_name, "owner": h.owner,
             "shares": h.shares, "close": to_float(h.close),
             "market_value": to_float(h.market_value)}
            for h in pf.holdings
        ],
    }
