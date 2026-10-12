import datetime as dt


def parse_roc_date(text: str) -> dt.date:
    """'1150929' → date(2026, 9, 29)。格式不對就丟出 ValueError。"""
    text = text.strip()
    if not text.isdigit() or len(text) not in (6, 7):
        raise ValueError(f"不是民國日期：{text!r}")
    year = int(text[:-4]) + 1911
    month = int(text[-4:-2])
    day = int(text[-2:])
    return dt.date(year, month, day)