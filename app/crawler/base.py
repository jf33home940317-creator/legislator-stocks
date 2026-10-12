import datetime as dt
import time
from collections.abc import Callable
from typing import Any

import httpx
from sqlalchemy.orm import Session, sessionmaker

from app.models import CrawlLog

USER_AGENT = "legislator-stocks-class-project/0.1"

# 爬蟲工作：接收 session，回傳（寫入筆數, 備註訊息）
Job = Callable[[Session], tuple[int, str | None]]


class CrawlError(Exception):
    """資料格式不符合預期這類錯誤，整批資料都不應該寫入。"""


def fetch_json(url: str, *, retries: int = 3, backoff: float = 1.0,
               client: httpx.Client | None = None,
               sleep: Callable[[float], None] = time.sleep) -> Any:
    """抓取網址的 JSON。遇到網路錯誤或 5xx 會自動重試，每次等待時間加倍。"""
    own_client = client is None
    if client is None:
        client = httpx.Client(timeout=30, follow_redirects=True,
                              headers={"User-Agent": USER_AGENT})
    try:
        for attempt in range(retries + 1):
            try:
                response = client.get(url)
                response.raise_for_status()
                return response.json()
            except (httpx.TransportError, httpx.HTTPStatusError) as exc:
                retryable = (isinstance(exc, httpx.TransportError)
                             or exc.response.status_code >= 500)
                if not retryable or attempt == retries:
                    raise
                sleep(backoff * 2 ** attempt)
    finally:
        if own_client:
            client.close()


def _utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)


def run_crawler(session_factory: sessionmaker, source: str, job: Job) -> CrawlLog:
    """執行一個爬蟲工作，並在 crawl_log 留下紀錄。

    工作寫入的資料和「成功」的紀錄在同一次 commit 送出；
    中途出錯就 rollback，資料庫裡不會留下寫到一半的資料，只留下一筆「失敗」紀錄。
    """
    with session_factory() as session:
        log = CrawlLog(source=source, started_at=_utcnow(), status="running", rows=0)
        session.add(log)
        session.commit()

        try:
            rows, message = job(session)
            log.status, log.rows, log.message = "success", rows, message
        except Exception as exc:  # noqa: BLE001  任何錯誤都要記錄下來，不能讓 cron 默默失敗
            session.rollback()
            log.status, log.message = "failed", f"{type(exc).__name__}: {exc}"

        log.finished_at = _utcnow()
        session.commit()
        session.refresh(log)
        return log
