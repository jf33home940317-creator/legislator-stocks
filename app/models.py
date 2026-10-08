import datetime as dt
from decimal import Decimal

from sqlalchemy import CheckConstraint, Date, ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base

MARKETS = ("TWSE", "TPEx", "ESB")   # 上市、上櫃、興櫃


def _in(column: str, values: tuple[str, ...]) -> str:
    """產生 SQL 條件，例如 market IN ('TWSE', 'TPEx', 'ESB')"""
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


class Stock(Base):                                                  # ①
    __tablename__ = "stock"                                          # ②
    __table_args__ = (CheckConstraint(_in("market", MARKETS), name="market"),)

    code: Mapped[str] = mapped_column(String(10), primary_key=True)             # ③
    name: Mapped[str] = mapped_column(String(100))                 # ④
    market: Mapped[str] = mapped_column(String(4))


class StockPrice(Base):
    __tablename__ = "stock_price"

    stock_code: Mapped[str] = mapped_column(ForeignKey("stock.code"), primary_key=True)   # ⑤
    date: Mapped[dt.date] = mapped_column(Date, primary_key=True)                                # ⑥
    close: Mapped[Decimal] = mapped_column(Numeric(12, 2))                              # ⑦