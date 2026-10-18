"""監察院 PDF → 待人工審核的持股 CSV（半自動流程的「自動」那一半）。

審核 CSV 前 6 欄就是 import_holdings 要的欄位；後面幾欄給人看。
有 problem 的列 stock_code 或 owner 會是空的，import_holdings 會整份拒絕，
所以一定要人工修好（或刪掉那列）才匯得進去。
"""
import csv
import re
import time
from collections.abc import Iterable
from pathlib import Path

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.crawler.base import CrawlError
from app.crawler.declarations import cy_pdf
from app.crawler.declarations.csv_import import HOLDING_COLUMNS
from app.crawler.declarations.pdf_parse import (
    Header, StockLine, owner_of, parse_header, parse_stock_tables, pdf_tables, pdf_text,
    stated_stock_total, totals_match)
from app.models import Politician, Stock

PDF_DIR = Path("data/pdfs")
ALIASES = Path("seed/stock_aliases.csv")
REVIEW_COLUMNS = HOLDING_COLUMNS + ["stock_name", "holder", "raw", "problem"]


def chinese_name(name: str) -> str:
    """'伍麗華Saidhai‧Tahovecahe' → '伍麗華'：監察院只認中文名。"""
    match = re.match(r"[一-鿿]+", name)
    return match.group(0) if match else name


def load_aliases(path: Path = ALIASES) -> dict[str, str]:
    """人工確認過的「PDF 名稱 → 股票代號」對照表。"""
    if not path.exists():
        return {}
    with open(path, encoding="utf-8-sig", newline="") as f:
        return {row["pdf_name"].strip(): row["stock_code"].strip() for row in csv.DictReader(f)}


def normalize_name(name: str) -> str:
    """固定規則統一寫法（不是模糊比對）：
    「台泥「交付臺灣銀行信託」」→「台泥」、「臺化」→「台化」、「國巨＊」→「國巨」"""
    name = re.sub(r"「[^」]*」", "", name)
    return name.replace("臺", "台").replace("＊", "").replace("*", "").strip()


def name_index(stocks: Iterable[tuple[str, str]]) -> dict[str, str]:
    """（代號, 名稱）→ {名稱: 代號}，另外加上正規化後的名稱（DB 裡也有「國巨*」這種寫法）。
    正規化後撞名的就不加，寧可對不上交給人工，也不要對錯。"""
    index = {name: code for code, name in stocks}
    normalized: dict[str, set[str]] = {}
    for name, code in index.items():
        normalized.setdefault(normalize_name(name), set()).add(code)
    for name, codes in normalized.items():
        if name not in index and len(codes) == 1:
            index[name] = codes.pop()
    return index


def match_code(name: str, codes_by_name: dict[str, str], aliases: dict[str, str]) -> str | None:
    """依序試：原名 → 別名表 → 正規化後的名稱 → 正規化後查別名表。對不上回傳 None，絕不模糊猜測。"""
    for candidate in (name, normalize_name(name)):
        code = codes_by_name.get(candidate) or aliases.get(candidate)
        if code:
            return code
    return None


def review_rows(politician_id: int, header: Header, stocks: list[StockLine], stated_total: int | None,
                source_url: str, codes_by_name: dict[str, str], aliases: dict[str, str]) -> list[dict]:
    """把一份申報的股票轉成審核 CSV 的列。"""
    total_ok = totals_match(stocks, stated_total)
    rows = []
    for stock in stocks:
        code = None if stock.currency else match_code(stock.name, codes_by_name, aliases)
        owner = owner_of(stock.holder, header)
        problems = []
        if stock.currency:
            problems.append(f"外國股票（{stock.currency}），沒有台股股價")
        elif code is None:
            problems.append("找不到股票代號（下市/未上市？或補進 stock_aliases.csv）")
        if owner is None:
            problems.append(f"所有人 {stock.holder} 不是本人/配偶/子女")
        if not total_ok:
            problems.append(f"這份申報各列加總≠表上總價額 {stated_total}，可能漏抓")
        rows.append({
            "politician_id": politician_id,
            "declared_date": header.declared_date.isoformat(),
            "source_url": source_url,
            "stock_code": code or "",
            "owner": owner or "",
            "shares": stock.shares,
            "stock_name": stock.name,
            "holder": stock.holder,
            "raw": stock.raw,
            "problem": "；".join(problems),
        })
    return rows


def write_review_csv(rows: Iterable[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # utf-8-sig：讓 Excel 打開不會變亂碼
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=REVIEW_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def review_one(client, session: Session, name: str, codes_by_name: dict[str, str],
               aliases: dict[str, str], delay: float) -> tuple[list[dict], str]:
    """處理一位立委：查詢 → 下載（已下載就用舊檔）→ 解析。回傳（審核列, 備註）。"""
    name = name.strip()   # 名單檔可能帶 Windows 換行字元 CR，看不見但會讓比對失敗
    # 用 startswith：輸入「伍麗華」也找得到「伍麗華Saidhai‧Tahovecahe」
    politician = session.scalars(select(Politician).where(Politician.name.startswith(name))).first()
    if politician is None:
        raise CrawlError("資料庫沒有這位立委，請先跑 python -m app.crawler legislators")
    query_name = chinese_name(name)
    latest = cy_pdf.pick_latest(cy_pdf.query_declarations(client, query_name))
    time.sleep(delay)   # 對政府網站客氣一點
    if latest is None:
        return [], "查無立法院一般申報"

    path = PDF_DIR / f"{query_name}_{latest['Period']}.pdf"
    if not path.exists():
        cy_pdf.save_pdf(cy_pdf.download_pdf(client, latest["Id"]), path)
        time.sleep(delay)

    text = pdf_text(path)
    header = parse_header(text)
    # 防止把別人的持股掛到這位立委身上。罕見字（陳秀寳的「寳」）PDF 抽不出來，
    # 只要 PDF 的名字是查詢名字的開頭就放行，但每列都標註給人工確認
    name_note = None
    if header.declarant != query_name:
        if len(header.declarant) < 2 or not query_name.startswith(header.declarant):
            raise CrawlError(f"PDF 申報人是 {header.declarant}，不是 {query_name}")
        name_note = f"PDF 申報人名字抽成「{header.declarant}」（缺字），請確認是 {query_name}"
    stocks = parse_stock_tables(pdf_tables(path))
    stated = stated_stock_total(text)
    # 下載 API 用 POST，沒有固定網址 → 記下「第幾期第幾頁」讓人查得到
    source = f"{cy_pdf.BASE}/layout/baselist#第{latest['Period']}期{latest['PublishPage']}"
    rows = review_rows(politician.id, header, stocks, stated, source, codes_by_name, aliases)
    if name_note:
        for row in rows:
            row["problem"] = "；".join(filter(None, [row["problem"], name_note]))
    bad = sum(1 for r in rows if r["problem"])
    return rows, (f"{len(rows)} 檔" + (f"（{bad} 檔待處理）" if bad else "") if rows else "本欄空白")


def build_review(session: Session, names: list[str], out: Path, *, delay: float = 1.0) -> tuple[int, str]:
    """對每位立委跑 review_one，寫成一份審核 CSV。回傳（列數, 摘要）。

    一位出錯不影響其他人：錯誤記在摘要裡，最後再人工處理。
    """
    codes_by_name = name_index(session.execute(select(Stock.code, Stock.name)))
    aliases = load_aliases()
    rows: list[dict] = []
    failed: list[str] = []

    with cy_pdf.make_client() as client:
        for i, name in enumerate(names, start=1):
            try:
                person, note = review_one(client, session, name, codes_by_name, aliases, delay)
            except (CrawlError, httpx.HTTPError, ValueError, KeyError) as exc:
                person, note = [], f"失敗 {type(exc).__name__}: {exc}"
                failed.append(f"{name}（{note}）")
            rows += person
            print(f"[{i}/{len(names)}] {name}: {note}", flush=True)   # 跑很久，邊跑邊印進度

    write_review_csv(rows, out)
    holders = len({r["politician_id"] for r in rows})
    summary = f"{len(names)} 位：{holders} 位有股票，失敗 {len(failed)} 位"
    return len(rows), summary + ("。失敗：" + "；".join(failed) if failed else "")
