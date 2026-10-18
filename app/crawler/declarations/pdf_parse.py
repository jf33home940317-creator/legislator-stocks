"""解析監察院財產申報 PDF：表頭（申報人、申報日、家屬）＋「(八)有價證券 1.股票」。

做法：pdfplumber 只負責把 PDF 轉成純文字，其餘都是字串處理，
所以除了 pdf_text() 以外，每個函式都可以直接拿一段文字來測試。
"""
import datetime as dt
import re
from dataclasses import dataclass
from pathlib import Path

import pdfplumber

from app.crawler.base import CrawlError


@dataclass(frozen=True)
class StockLine:
    name: str       # 股票簡稱，例如「力積電」（PDF 裡沒有代號）
    holder: str     # 所有人姓名，例如「謝俊雄」
    shares: int
    total: int      # 新臺幣總額＝股數 × 票面（不是市值）
    raw: str        # PDF 原文，人工校正時方便對照


@dataclass(frozen=True)
class Header:
    declarant: str                  # 申報人
    declared_date: dt.date          # 申報日（不是監察院的公告日）
    spouses: tuple[str, ...]
    children: tuple[str, ...]       # 未成年子女，名字會打碼，例如「謝○均」


# 一行股票：名稱 所有人 股數 票面價額 [外幣幣別] 新臺幣總額
#   例：「高興昌 謝俊雄 16,000 10 160,000」
STOCK_ROW = re.compile(
    r"^(?P<name>\S+) (?P<holder>\S+) (?P<shares>[\d,]+) (?P<face>[\d.,]+) "
    r"(?:(?P<currency>\S+) )?(?P<total>[\d,]+)$")
STOCK_START = "1.股票（總價額"
STOCK_END = "2.債券"


def pdf_text(path: Path) -> str:
    """把整份 PDF 每一頁的文字接起來。"""
    with pdfplumber.open(path) as pdf:
        return "\n".join(page.extract_text() or "" for page in pdf.pages)


def _int(text: str) -> int:
    return int(text.replace(",", ""))


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


def parse_stocks(text: str) -> tuple[list[StockLine], int | None]:
    """抓「1.股票」那一節。回傳（每一列股票, 表上寫的總價額）；本欄空白時是 ([], None)。

    頁尾（監察院公報…）和跨頁重印的欄位標題對不上 STOCK_ROW，會自然被跳過。
    """
    start = text.find(STOCK_START)
    if start == -1:
        raise CrawlError("找不到「1.股票」這一節，PDF 格式可能改了")
    end = text.find(STOCK_END, start)
    section = text[start:end if end != -1 else None]

    stated = re.search(r"總價額：新臺幣\s*([\d,]+)\s*元", section.splitlines()[0])
    lines = []
    for raw in section.splitlines()[1:]:
        match = STOCK_ROW.match(raw.strip())
        if match:
            lines.append(StockLine(
                name=match["name"], holder=match["holder"], shares=_int(match["shares"]),
                total=_int(match["total"]), raw=raw.strip()))
    return lines, _int(stated.group(1)) if stated else None


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
