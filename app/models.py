import datetime as dt
from decimal import Decimal

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base

# 每個欄位允許的值，集中寫在這裡，其他程式（例如 CSV 匯入）也會用到
ROLES = ("legislator", "councilor")                      # 立委、議員
PARSE_STATUSES = ("pending", "parsed", "verified", "failed")
OWNERS = ("本人", "配偶", "未成年子女")
MARKETS = ("TWSE", "TPEx", "ESB")                        # 上市、上櫃、興櫃
CRAWL_STATUSES = ("running", "success", "failed")


def _in(column: str, values: tuple[str, ...]) -> str:
    """產生 SQL 條件，例如 market IN ('TWSE', 'TPEx', 'ESB')"""
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


class Politician(Base):
    """政治人物"""
    __tablename__ = "politician"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(50))
    name_alt: Mapped[str | None] = mapped_column(String(100))   # 族語名／羅馬拼音
    photo_url: Mapped[str | None] = mapped_column(Text)

    # 一個人有很多任期、很多份申報
    terms: Mapped[list["Term"]] = relationship(
        back_populates="politician", order_by="Term.start_date", cascade="all, delete-orphan")
    declarations: Mapped[list["Declaration"]] = relationship(
        back_populates="politician", cascade="all, delete-orphan")

    @property
    def current_term(self) -> "Term | None":
        """最新（開始日期最晚）的任期。"""
        return self.terms[-1] if self.terms else None


class Term(Base):
    """任期：同一個人可能當過很多屆，黨籍也可能改變"""
    __tablename__ = "term"
    __table_args__ = (CheckConstraint(_in("role", ROLES), name="role"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    politician_id: Mapped[int] = mapped_column(
        ForeignKey("politician.id", ondelete="CASCADE"), index=True)
    role: Mapped[str] = mapped_column(String(20))
    session: Mapped[str] = mapped_column(String(20))            # 例如「第11屆」
    district: Mapped[str | None] = mapped_column(String(50))    # 選區，不分區為空
    party: Mapped[str] = mapped_column(String(50))
    start_date: Mapped[dt.date] = mapped_column(Date)
    end_date: Mapped[dt.date | None] = mapped_column(Date)      # 現任為空

    politician: Mapped[Politician] = relationship(back_populates="terms")


class Declaration(Base):
    """一份財產申報"""
    __tablename__ = "declaration"
    __table_args__ = (CheckConstraint(_in("parse_status", PARSE_STATUSES), name="parse_status"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    politician_id: Mapped[int] = mapped_column(
        ForeignKey("politician.id", ondelete="CASCADE"), index=True)
    declared_date: Mapped[dt.date] = mapped_column(Date)
    source_url: Mapped[str] = mapped_column(Text)               # 監察院 PDF 網址
    pdf_sha256: Mapped[str | None] = mapped_column(String(64), unique=True)
    parse_status: Mapped[str] = mapped_column(String(10), default="pending")

    politician: Mapped[Politician] = relationship(back_populates="declarations")
    holdings: Mapped[list["Holding"]] = relationship(
        back_populates="declaration", cascade="all, delete-orphan")


class Stock(Base):
    """股票"""
    __tablename__ = "stock"
    __table_args__ = (CheckConstraint(_in("market", MARKETS), name="market"),)

    code: Mapped[str] = mapped_column(String(10), primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    market: Mapped[str] = mapped_column(String(4))


class Holding(Base):
    """申報裡的一筆持股"""
    __tablename__ = "holding"
    __table_args__ = (
        CheckConstraint("shares > 0", name="shares_positive"),
        CheckConstraint(_in("owner", OWNERS), name="owner"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    declaration_id: Mapped[int] = mapped_column(
        ForeignKey("declaration.id", ondelete="CASCADE"), index=True)
    stock_code: Mapped[str] = mapped_column(ForeignKey("stock.code"), index=True)
    owner: Mapped[str] = mapped_column(String(10))
    shares: Mapped[int]
    raw_text: Mapped[str | None] = mapped_column(Text)          # PDF 原文，方便查錯

    declaration: Mapped[Declaration] = relationship(back_populates="holdings")
    stock: Mapped[Stock] = relationship()


class StockPrice(Base):
    """每日收盤價"""
    __tablename__ = "stock_price"

    stock_code: Mapped[str] = mapped_column(ForeignKey("stock.code"), primary_key=True)
    date: Mapped[dt.date] = mapped_column(Date, primary_key=True)
    close: Mapped[Decimal] = mapped_column(Numeric(12, 2))


class CrawlLog(Base):
    """爬蟲每次執行的紀錄"""
    __tablename__ = "crawl_log"
    __table_args__ = (CheckConstraint(_in("status", CRAWL_STATUSES), name="status"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    source: Mapped[str] = mapped_column(String(50))             # 例如 twse_prices
    started_at: Mapped[dt.datetime] = mapped_column(DateTime)
    finished_at: Mapped[dt.datetime | None] = mapped_column(DateTime)
    status: Mapped[str] = mapped_column(String(10))
    rows: Mapped[int] = mapped_column(default=0)
    message: Mapped[str | None] = mapped_column(Text)
