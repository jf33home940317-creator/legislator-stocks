import csv
import datetime as dt
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import OWNERS, ROLES, Declaration, Holding, Politician, Stock, Term

POLITICIAN_COLUMNS = ["id", "name", "name_alt", "photo_url", "role", "session",
                      "district", "party", "start_date", "end_date"]
HOLDING_COLUMNS = ["politician_id", "declared_date", "source_url", "stock_code",
                   "owner", "shares"]


class CsvImportError(ValueError):
    """CSV 內容有問題（欄位缺少、格式錯、找不到對應資料）時丟出，整批不匯入。"""


def _read(path: Path, columns: list[str]) -> list[tuple[int, dict[str, str]]]:
    # utf-8-sig：Excel 存的 CSV 開頭會有 BOM，這個編碼會自動去掉
    with open(path, encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        missing = set(columns) - set(reader.fieldnames or [])
        if missing:
            raise CsvImportError(f"{path} 缺少欄位：{sorted(missing)}")
        return list(enumerate(reader, start=2))  # 第 1 行是標題，資料從第 2 行開始


def _optional(value: str | None) -> str | None:
    value = (value or "").strip()
    return value or None


def _required(row: dict[str, str], field: str, line: int) -> str:
    value = _optional(row.get(field))
    if value is None:
        raise CsvImportError(f"第 {line} 行：{field} 不能是空的")
    return value


def _int(row: dict[str, str], field: str, line: int) -> int:
    text = _required(row, field, line).replace(",", "")
    try:
        return int(text)
    except ValueError:
        raise CsvImportError(f"第 {line} 行：{field} 不是整數：{text!r}") from None


def _date(row: dict[str, str], field: str, line: int) -> dt.date:
    text = _required(row, field, line)
    try:
        return dt.date.fromisoformat(text)
    except ValueError:
        raise CsvImportError(f"第 {line} 行：{field} 不是 YYYY-MM-DD 格式：{text!r}") from None


def import_politicians(session: Session, path: Path) -> int:
    """匯入立委 + 任期。同一個 id 重新匯入會更新，不會重複新增。"""
    rows = _read(path, POLITICIAN_COLUMNS)
    for line, row in rows:
        politician_id = _int(row, "id", line)
        role = _required(row, "role", line)
        if role not in ROLES:
            raise CsvImportError(f"第 {line} 行：role 只能是 {ROLES}，收到 {role!r}")
        term_session = _required(row, "session", line)

        politician = session.get(Politician, politician_id) or Politician(id=politician_id)
        politician.name = _required(row, "name", line)
        politician.name_alt = _optional(row["name_alt"])
        politician.photo_url = _optional(row["photo_url"])
        session.add(politician)

        # 找同屆同職位的任期，有就更新、沒有就新增
        term = next((t for t in politician.terms
                     if t.role == role and t.session == term_session), None)
        if term is None:
            term = Term(role=role, session=term_session)
            politician.terms.append(term)
        term.district = _optional(row["district"])
        term.party = _required(row, "party", line)
        term.start_date = _date(row, "start_date", line)
        term.end_date = _date(row, "end_date", line) if _optional(row["end_date"]) else None

    session.flush()
    return len(rows)


def import_holdings(session: Session, path: Path) -> int:
    """匯入持股。同一位立委、同一申報日重新匯入會整份取代舊持股。"""
    rows = _read(path, HOLDING_COLUMNS)
    known_stocks = set(session.scalars(select(Stock.code)))
    groups: dict[tuple[int, dt.date], dict] = {}

    for line, row in rows:
        politician_id = _int(row, "politician_id", line)
        if session.get(Politician, politician_id) is None:
            raise CsvImportError(
                f"第 {line} 行：找不到 politician_id={politician_id}，請先匯入 politicians CSV")
        code = _required(row, "stock_code", line)
        if code not in known_stocks:
            raise CsvImportError(
                f"第 {line} 行：股票代號 {code} 不在資料庫，請先執行 python -m app.crawler prices")
        owner = _required(row, "owner", line)
        if owner not in OWNERS:
            raise CsvImportError(f"第 {line} 行：owner 只能是 {OWNERS}，收到 {owner!r}")
        shares = _int(row, "shares", line)
        if shares <= 0:
            raise CsvImportError(f"第 {line} 行：shares 必須大於 0")

        key = (politician_id, _date(row, "declared_date", line))
        group = groups.setdefault(key, {"source_url": _required(row, "source_url", line),
                                        "holdings": []})
        group["holdings"].append(Holding(stock_code=code, owner=owner, shares=shares))

    for (politician_id, declared_date), group in groups.items():
        declaration = session.scalars(select(Declaration).where(
            Declaration.politician_id == politician_id,
            Declaration.declared_date == declared_date,
        )).first()
        if declaration is None:
            declaration = Declaration(politician_id=politician_id, declared_date=declared_date)
            session.add(declaration)
        declaration.source_url = group["source_url"]
        declaration.parse_status = "verified"
        declaration.holdings = group["holdings"]  # delete-orphan 會刪掉舊的持股

    session.flush()
    return sum(len(g["holdings"]) for g in groups.values())
