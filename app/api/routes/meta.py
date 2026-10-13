from fastapi import APIRouter
from sqlalchemy import func, select

from app.api.deps import SessionDep
from app.api.schemas import Meta
from app.models import CrawlLog, Declaration, Politician, StockPrice
from app.services.valuation import USABLE_STATUSES

router = APIRouter(tags=["meta"])


@router.get("/meta", response_model=Meta)
def get_meta(session: SessionDep):
    return Meta(
        latest_price_date=session.scalar(select(func.max(StockPrice.date))),
        latest_declared_date=session.scalar(
            select(func.max(Declaration.declared_date))
            .where(Declaration.parse_status.in_(USABLE_STATUSES))),
        last_crawled_at=session.scalar(
            select(func.max(CrawlLog.finished_at)).where(CrawlLog.status == "success")),
        politician_count=session.scalar(select(func.count()).select_from(Politician)),
    )
