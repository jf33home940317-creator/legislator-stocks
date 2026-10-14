"""監察院財產申報：用姓名查詢 → 挑最新一份 → 下載 PDF。"""
import datetime as dt
import re
from pathlib import Path
from typing import Any

import httpx

from app.crawler.base import CrawlError
from app.crawler.utils import parse_roc_date

BASE = "https://priso.cy.gov.tw"
QUERY_URL = f"{BASE}/api/Query/QueryData"
FILE_URL = f"{BASE}/api/Query/getFile"
# 監察院會檢查請求是不是從它自己的網頁發出 → 要帶 Origin / Referer
HEADERS = {
    "Origin": BASE,
    "Referer": f"{BASE}/layout/baselist",
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/120 Safari/537.36"),
}


def make_client() -> httpx.Client:
    return httpx.Client(timeout=60, headers=HEADERS)


def publish_date(text: str) -> dt.date:
    """'民國115年 03月 19日' → date(2026, 3, 19)"""
    digits = re.sub(r"\D", "", text)  # ① 把非數字全部拿掉 → '1150319'
    return parse_roc_date(digits)


def query_declarations(client: httpx.Client, name: str) -> list[dict[str, Any]]:
    """用姓名查監察院，回傳這個人所有的申報紀錄（每筆是一個 dict）。"""
    body = {"Data": {"Type": "name", "Value": name},
            "Page": {"PageNo": 1, "PageSize": 200, "OrderByNum": 0, "OrderBySort": ""}}
    response = client.post(QUERY_URL, json=body)  # ② 用 client 發 POST：網址 QUERY_URL，body 當 JSON 送出
    response.raise_for_status()
    return response.json()["Data"]["Data"]      # ③ 從 response.json() 挖出那份清單


def pick_latest(items: list[dict[str, Any]]) -> dict[str, Any] | None:
    """只留「立法院」的「01一般申報」，回傳公告日最新的一筆；一筆都沒有就回傳 None。"""
    candidates = [item for item in items if item["Dept"] == "立法院" and item["PublishType"].startswith("01")]  # ④ Dept 是「立法院」而且 PublishType 開頭是 "01"
    if not candidates:
        return None
    return max(candidates, key=lambda p: publish_date(p["PublishDate"]))               # ⑤ 用 publish_date() 轉換後的 PublishDate 比大小


def download_pdf(client: httpx.Client, file_id: str) -> bytes:
    """用申報紀錄的 Id 下載 PDF，回傳原始 bytes。"""
    response = client.post(FILE_URL, json={"From": "base", "FileId": file_id})  # ① 用 client 發 POST：網址 FILE_URL，JSON 是 {"From": "base", "FileId": file_id}
    response.raise_for_status()
    content = response.content   # ② 拿回應「原封不動的 bytes」
    if not content.startswith(b"%PDF"):
        raise CrawlError(f"下載到的不是 PDF（開頭是 {content[:20]!r}），API 可能改了")
    return content


def save_pdf(content: bytes, path: Path) -> None:
    """把 PDF bytes 存到 path；資料夾不存在就自動建立。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "wb") as f:   # ③ 寫入「二進位」的模式
        f.write(content)
