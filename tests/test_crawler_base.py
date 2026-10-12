import httpx
import pytest
from sqlalchemy import select

from app.crawler.base import fetch_json, run_crawler
from app.models import CrawlLog, Stock


def mock_client(*responses):
    """做一個「假的伺服器」：依序回傳指定的回應，並記錄被呼叫了幾次。"""
    queue = list(responses)
    calls = []

    def handler(request):
        calls.append(request)
        item = queue.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    return httpx.Client(transport=httpx.MockTransport(handler)), calls


# ---------- fetch_json：重試 ----------

def test_fetch_json_retries_server_errors():
    client, calls = mock_client(httpx.Response(500), httpx.Response(503),
                                httpx.Response(200, json=[{"ok": 1}]))
    waits = []
    assert fetch_json("https://x.test", client=client, sleep=waits.append) == [{"ok": 1}]
    assert len(calls) == 3          # 試了 3 次才成功
    assert waits == [1.0, 2.0]      # 中間等了 1 秒、2 秒


def test_fetch_json_does_not_retry_404():
    client, calls = mock_client(httpx.Response(404))
    with pytest.raises(httpx.HTTPStatusError):
        fetch_json("https://x.test", client=client, sleep=lambda s: None)
    assert len(calls) == 1          # 404 再試也沒用，只試 1 次


def test_fetch_json_gives_up_after_retries():
    client, calls = mock_client(*[httpx.ConnectError("網路斷線") for _ in range(4)])
    with pytest.raises(httpx.ConnectError):
        fetch_json("https://x.test", client=client, retries=3, sleep=lambda s: None)
    assert len(calls) == 4          # 第 1 次 + 重試 3 次


# ---------- run_crawler：交易與執行紀錄 ----------

def test_run_crawler_success_commits_data_and_log(session_factory, session):
    def job(s):
        s.add(Stock(code="2330", name="台積電", market="TWSE"))
        return 1, "ok"

    log = run_crawler(session_factory, "demo", job)

    assert (log.status, log.rows, log.message) == ("success", 1, "ok")
    assert log.finished_at is not None
    assert session.get(Stock, "2330") is not None


def test_run_crawler_failure_rolls_back(session_factory, session):
    def job(s):
        s.add(Stock(code="2330", name="台積電", market="TWSE"))
        s.flush()
        raise RuntimeError("API 格式改了")

    log = run_crawler(session_factory, "demo", job)

    assert log.status == "failed"
    assert "API 格式改了" in log.message
    assert session.get(Stock, "2330") is None                       # 寫到一半的資料被取消了
    assert session.scalars(select(CrawlLog)).one().status == "failed"  # 但失敗紀錄有留下來
