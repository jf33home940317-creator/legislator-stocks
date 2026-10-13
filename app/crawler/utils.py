import datetime as dt
from decimal import Decimal, InvalidOperation



def parse_roc_date(text: str) -> dt.date:
    """'1150929' → date(2026, 9, 29)。格式不對就丟出 ValueError。"""
    text = text.strip()
    if not text.isdigit() or len(text) not in (6, 7):
        raise ValueError(f"不是民國日期：{text!r}")
    year = int(text[:-4]) + 1911
    month = int(text[-4:-2])
    day = int(text[-2:])
    return dt.date(year, month, day)


def parse_price(text: str | None) -> Decimal | None:
    """價格字串轉 Decimal；沒成交（空白、--、---、0）一律回傳 None，絕不回傳 0。"""
    if text is None:
        return None
    cleaned = text.strip().replace(",", "")      # ① 去掉千分位逗號
    try:
        value = Decimal(cleaned)
    except InvalidOperation:                               # ② Decimal 轉換失敗時的錯誤種類
        return None
    if not value.is_finite() or value <= 0:
        return None                            # ③ 0 或負數也代表沒有成交
    return value