import datetime as dt
import json

import httpx

from app.crawler.declarations.cy_pdf import QUERY_URL, pick_latest, publish_date, query_declarations


def item(dept: str, publish_type: str, date: str, id_: str = "x") -> dict:
    """做一筆假的監察院查詢結果（只放我們會用到的欄位）"""
    return {"Id": id_, "Dept": dept, "PublishType": publish_type, "PublishDate": date}


# ---------- ① publish_date ----------

def test_publish_date():
    assert publish_date("民國115年 03月 19日") == dt.date(2026, 3, 19)
    assert publish_date("民國99年 12月 01日") == dt.date(2010, 12, 1)


# ---------- ②③ query_declarations ----------

def test_query_declarations_posts_name_and_returns_list():
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json={"Success": True, "Data": {"Data": [item("立法院", "01一般申報", "民國115年 03月 19日")]}})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    result = query_declarations(client, "王小明")

    assert len(result) == 1 and result[0]["Dept"] == "立法院"
    assert calls[0].method == "POST"
    assert str(calls[0].url) == QUERY_URL
    assert json.loads(calls[0].content)["Data"]["Value"] == "王小明"


# ---------- ④⑤ pick_latest ----------

def test_pick_latest_filters_dept_and_type_then_takes_newest():
    items = [
        item("立法院", "01一般申報", "民國113年 07月 23日", "old"),
        item("立法院", "01一般申報", "民國115年 03月 19日", "new"),
        item("立法院", "04信託申報", "民國115年 10月 01日", "trust"),   # 信託申報：不要
        item("高雄市政府", "01一般申報", "民國116年 01月 01日", "kh"),  # 別的機關：不要
    ]
    assert pick_latest(items)["Id"] == "new"


def test_pick_latest_returns_none_when_nothing_matches():
    assert pick_latest([item("高雄市政府", "01一般申報", "民國109年 10月 16日")]) is None
    assert pick_latest([]) is None
