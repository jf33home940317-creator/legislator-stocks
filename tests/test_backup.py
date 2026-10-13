import datetime as dt
import sqlite3
from contextlib import closing

from app.backup import backup


def test_backup_copies_data_and_keeps_latest(tmp_path):
    db = tmp_path / "app.db"
    with closing(sqlite3.connect(db)) as conn:
        conn.execute("CREATE TABLE t (x INTEGER)")
        conn.execute("INSERT INTO t VALUES (42)")
        conn.commit()

    backup_dir = tmp_path / "backups"
    backup_dir.mkdir()
    for day in range(1, 10):  # 先放 9 份舊備份
        (backup_dir / f"app-2026-09-0{day}.db").write_bytes(b"")

    target = backup(db, backup_dir, keep=7, today=dt.date(2026, 9, 30))

    assert target.name == "app-2026-09-30.db"
    with closing(sqlite3.connect(target)) as conn:
        assert conn.execute("SELECT x FROM t").fetchone() == (42,)
    remaining = sorted(p.name for p in backup_dir.glob("app-*.db"))
    assert len(remaining) == 7                       # 只保留 7 份
    assert remaining[-1] == "app-2026-09-30.db"
    assert "app-2026-09-01.db" not in remaining      # 最舊的被刪掉
