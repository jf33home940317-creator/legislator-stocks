import datetime as dt
import json
import re
import ssl
from dataclasses import dataclass
from typing import Any

import httpx
from sqlalchemy.orm import Session

from app.crawler.base import CrawlError
from app.models import Politician, Term

# 立法院開放資料：第 11 屆委員個人資訊
URL = "https://data.ly.gov.tw/odw/ID16Action.action?term=11&fileType=json"
SESSION_NAME = "第11屆"
# 瀏覽器 User-Agent：這台伺服器會擋掉非瀏覽器的請求
BROWSER_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/120 Safari/537.36")


@dataclass(frozen=True)
class LegislatorRow:
    id: int
    name: str
    party: str
    district: str | None   # 不分區為 None
    photo_url: str
    start_date: dt.date


def _fetch() -> Any:
    """
    對付立法院這台「挑剔」的伺服器：
    1. 它用舊版 SSL renegotiation → 要打開 OP_LEGACY_SERVER_CONNECT(0x4)
    2. 它會擋非瀏覽器 → 要帶瀏覽器 User-Agent
    3. 它「謊報」回傳是 gzip、其實是純文字 → 我們自己讀原始 bytes 再 decode，不讓 httpx 誤解壓
    """
    ctx = ssl.create_default_context()
    ctx.options |= 0x4  # OP_LEGACY_SERVER_CONNECT
    response = httpx.get(URL, timeout=40, verify=ctx,
                         headers={"User-Agent": BROWSER_UA, "Accept-Encoding": "gzip"})
    response.raise_for_status()
    return json.loads(response.content.decode("utf-8"))


def _roc_slash_date(text: str) -> dt.date:
    """'2024/02/01' → date(2024, 2, 1)（這個 API 的到職日已是西元年）"""
    year, month, day = (int(p) for p in text.strip().split("/"))
    return dt.date(year, month, day)


def parse(data: Any) -> tuple[list[LegislatorRow], int]:
    """把立法院 JSON 轉成 LegislatorRow。只保留現任，回傳（資料列, 跳過筆數）。"""
    if not isinstance(data, dict) or "dataList" not in data:
        raise CrawlError("回應缺少 dataList，API 格式可能改了")
    items = data["dataList"]
    if not items or not {"name", "party", "areaName", "picUrl"} <= set(items[0]):
        raise CrawlError("dataList 是空的或缺少欄位，API 格式可能改了")

    rows: list[LegislatorRow] = []
    skipped = 0
    for item in items:
        if item.get("leaveFlag") == "是":      # 跳過已離職
            skipped += 1
            continue
        match = re.search(r"/(\d+)\.jpg", item.get("picUrl", ""))
        if not match:                           # 沒有照片編號就沒有穩定 id，跳過
            skipped += 1
            continue
        area = (item.get("areaName") or "").strip()
        district = None if "不分區" in area else area   # 不分區存成 None
        photo = re.sub(r"(?<!:)//", "/", item["picUrl"]).replace("http://", "https://")
        rows.append(LegislatorRow(
            id=int(match.group(1)),
            name=item["name"].strip(),
            party=(item.get("party") or "無黨籍").strip(),
            district=district,
            photo_url=photo,
            start_date=_roc_slash_date(item["onboardDate"]),
        ))
    return rows, skipped


def save_legislators(session: Session, rows: list[LegislatorRow]) -> int:
    """upsert 立委與其第 11 屆任期。重跑會更新，不會重複。"""
    for row in rows:
        politician = session.get(Politician, row.id) or Politician(id=row.id)
        politician.name = row.name
        politician.photo_url = row.photo_url
        session.add(politician)

        term = next((t for t in politician.terms
                     if t.role == "legislator" and t.session == SESSION_NAME), None)
        if term is None:
            term = Term(role="legislator", session=SESSION_NAME)
            politician.terms.append(term)
        term.party = row.party
        term.district = row.district
        term.start_date = row.start_date
    session.flush()
    return len(rows)


def job(session: Session) -> tuple[int, str | None]:
    rows, skipped = parse(_fetch())
    saved = save_legislators(session, rows)
    return saved, f"現任 {saved} 位，跳過 {skipped} 位（離職或無編號）"
