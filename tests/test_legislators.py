import datetime as dt
import json
from pathlib import Path

from app.crawler import legislators
from app.crawler.legislators import LegislatorRow
from app.models import Politician

FIXTURE = Path(__file__).parent / "fixtures" / "ly_legislators.json"


def load():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def test_parse_skips_leavers_and_maps_fields():
    rows, skipped = legislators.parse(load())
    assert skipped == 1  # 已離職者被跳過
    assert rows[0] == LegislatorRow(
        id=110001, name="丁學忠", party="中國國民黨", district="雲林縣第1選舉區",
        photo_url="https://www.ly.gov.tw/Images/Legislators/110001.jpg",
        start_date=dt.date(2024, 2, 1))


def test_parse_district_none_for_at_large():
    rows, _ = legislators.parse(load())
    wang = next(r for r in rows if r.name == "王小華")
    assert wang.district is None  # 不分區存成 None


def test_save_and_reimport_updates(session, monkeypatch):
    monkeypatch.setattr(legislators, "_fetch", load)
    saved, message = legislators.job(session)
    session.commit()
    assert saved == 2
    p = session.get(Politician, 110001)
    assert p.name == "丁學忠"
    assert p.current_term.party == "中國國民黨"

    # 第二次執行：改黨籍，應更新而非重複
    data = load()
    data["dataList"][0]["party"] = "無黨籍"
    monkeypatch.setattr(legislators, "_fetch", lambda: data)
    legislators.job(session)
    session.commit()
    p = session.get(Politician, 110001)
    assert len(p.terms) == 1
    assert p.current_term.party == "無黨籍"
