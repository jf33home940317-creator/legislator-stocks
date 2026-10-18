"""解析監察院財產申報 PDF：表頭（申報人、申報日、家屬）＋「(八)有價證券 1.股票」。

做法：
- 表頭、表上寫的總價額：用 pdf_text() 抽出的純文字 + 正規表示式
- 股票每一列：用 pdf_tables() 依 PDF 的格線抽表格。名稱太長會換行
  （「華南金「交付臺灣銀行信 / 託」」），純文字看不出哪段屬於哪一列，表格才分得清楚。
pdfplumber 只出現在 pdf_text() / pdf_tables()，其餘函式都可以直接拿文字或 list 來測試。
"""
import datetime as dt
import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path

import pdfplumber

from app.crawler.base import CrawlError

Table = list[list[str | None]]   # pdfplumber 的表格：一列是一個 list，每格是字串或 None


@dataclass(frozen=True)
class StockLine:
    name: str           # 股票名稱，例如「力積電」「台泥「交付臺灣銀行信託」」（PDF 裡沒有代號）
    holder: str         # 所有人姓名，例如「謝俊雄」
    shares: int
    total: Decimal      # 新臺幣總額＝股數 × 票面（不是市值）；外國股票會有小數
    currency: str       # 外幣幣別，台股是空字串
    raw: str            # PDF 原文，人工校正時方便對照


@dataclass(frozen=True)
class Header:
    declarant: str                  # 申報人
    declared_date: dt.date          # 申報日（不是監察院的公告日）
    spouses: tuple[str, ...]
    children: tuple[str, ...]       # 未成年子女，名字會打碼，例如「謝○均」


STOCK_START = "1.股票（總價額"
STOCK_HEADER = ["名稱", "所有人", "股數", "票面價額", "外幣幣別"]   # 股票表的前 5 欄


def pdf_text(path: Path) -> str:
    """把整份 PDF 每一頁的文字接起來。"""
    with pdfplumber.open(path) as pdf:
        return "\n".join(page.extract_text() or "" for page in pdf.pages)


def pdf_tables(path: Path) -> list[Table]:
    """抽出整份 PDF 每一頁的所有表格（依頁碼順序）。"""
    with pdfplumber.open(path) as pdf:
        return [table for page in pdf.pages for table in page.extract_tables()]


def parse_header(text: str) -> Header:
    """從第 1 頁表頭抓申報人、申報日、配偶與未成年子女。"""
    name = re.search(r"申報人姓名\s*(\S+)", text)
    # [^\n]*? 跳過中間的雜訊：有的 PDF 會抽出「申 報 日 1★114年11月01日」
    date = re.search(r"申\s*報\s*日[^\n]*?(\d{2,3})\s*年\s*(\d+)\s*月\s*(\d+)\s*日", text)
    if not name or not date:
        raise CrawlError("找不到申報人姓名或申報日，PDF 格式可能改了")

    year, month, day = (int(g) for g in date.groups())
    # 表頭一行可能有兩組，例如「配偶 謝俊雄 未成年子女 謝○均」→ findall 全部抓出來
    family = re.findall(r"(配偶|未成年子女)\s+(\S+)", text[:text.find("（二）")])
    return Header(
        declarant=name.group(1),
        declared_date=dt.date(year + 1911, month, day),
        spouses=tuple(n for role, n in family if role == "配偶"),
        children=tuple(n for role, n in family if role == "未成年子女"),
    )


def stated_stock_total(text: str) -> int | None:
    """表上寫的股票總價額；本欄空白時是 None。用來和每列加總對帳。"""
    start = text.find(STOCK_START)
    if start == -1:
        raise CrawlError("找不到「1.股票」這一節，PDF 格式可能改了")
    first_line = text[start:].splitlines()[0]
    match = re.search(r"總價額：新臺幣\s*([\d,]+)\s*元", first_line)
    return int(match.group(1).replace(",", "")) if match else None


def _clean(cell: str | None) -> str:
    """格子裡的換行接回去，例如「華南金「交付臺灣銀行信\\n託」」→「華南金「交付臺灣銀行信託」」"""
    return (cell or "").replace("\n", "").strip()


def _number(text: str) -> Decimal | None:
    try:
        return Decimal(text.replace(",", ""))
    except InvalidOperation:
        return None


def is_stock_table(table: Table) -> bool:
    """第一列是「名稱 所有人 股數 票面價額 外幣幣別 …」的就是股票表（債券、基金表的欄位不一樣）。"""
    if not table or len(table[0]) != 6:
        return False
    return [_clean(c).replace(" ", "") for c in table[0][:5]] == STOCK_HEADER


def _is_continuation(table: Table) -> bool:
    """跨頁的接續表格沒有標題列：6 欄、而且第一個有股數的列，股數是數字。

    標題列剛好在頁底時，標題第二行「總 額」會被擠到下一頁，變成 ['', '', '', '', '', '總 額']，
    所以要跳過股數格是空的列再判斷。
    """
    if len(table[0]) != 6:
        return False
    first = next((row for row in table if _clean(row[2])), None)
    return first is not None and _number(_clean(first[2])) is not None


def _stock_rows(tables: list[Table]) -> list[list[str | None]]:
    """股票表（去掉標題列）＋緊跟在後面的接續表格；碰到別的有標題的表格就停止。

    注意存款表跨頁時也會出現「沒有標題的 6 欄表格」，所以只認股票表「後面」的接續。
    """
    rows: list[list[str | None]] = []
    in_stock = False
    for table in tables:
        if is_stock_table(table):
            in_stock = True
            rows += table[1:]
        elif in_stock and _is_continuation(table):
            rows += table
        else:
            in_stock = False
    return rows


def parse_stock_tables(tables: list[Table]) -> list[StockLine]:
    """從所有表格裡挑出股票那幾列，轉成 StockLine。「本欄空白」或股數不是數字的列直接跳過。"""
    lines = []
    for row in _stock_rows(tables):
        if len(row) != 6:
            continue
        name, holder, shares, _face, currency, total = (_clean(c) for c in row)
        shares_n, total_n = _number(shares), _number(total)
        if not name or shares_n is None or total_n is None:
            continue
        lines.append(StockLine(
            name=name,
            holder=holder.replace(" ", ""),     # 信託股票的所有人會抽成「林 楚茵」
            shares=int(shares_n),
            total=total_n,
            currency=currency,
            raw=" ".join(_clean(c) for c in row if _clean(c)),
        ))
    return lines


def totals_match(lines: list[StockLine], stated: int | None) -> bool:
    """每列加總是否等於表上總價額。外幣換算會有小數，差在列數（每列最多四捨五入差 1 元）以內都算對。"""
    if stated is None:
        return not lines
    return abs(sum(line.total for line in lines) - stated) <= max(1, len(lines))


def _masked_equal(masked: str, name: str) -> bool:
    """「謝○均」和「謝俊均」視為同一人：長度一樣、○ 以外的字都相同。"""
    return len(masked) == len(name) and all(m in ("○", c) for m, c in zip(masked, name))


def owner_of(holder: str, header: Header) -> str | None:
    """把所有人姓名換成資料庫用的身分；對不上回傳 None（留給人工判斷）。"""
    if holder == header.declarant:
        return "本人"
    if holder in header.spouses:
        return "配偶"
    if any(_masked_equal(child, holder) or child == holder for child in header.children):
        return "未成年子女"
    return None
