import datetime as dt
import sqlite3
import sys
from contextlib import closing
from pathlib import Path

from sqlalchemy.engine import make_url

from app.config import settings


def backup(db_path: Path, backup_dir: Path, keep: int = 7,
           today: dt.date | None = None) -> Path:
    """用 SQLite 的 backup API 安全複製資料庫（執行中也能備份），只保留最近 keep 份。"""
    backup_dir.mkdir(parents=True, exist_ok=True)
    target = backup_dir / f"app-{(today or dt.date.today()).isoformat()}.db"
    with closing(sqlite3.connect(db_path)) as src, closing(sqlite3.connect(target)) as dst:
        src.backup(dst)
    for old in sorted(backup_dir.glob("app-*.db"))[:-keep]:
        old.unlink()
    return target


def main() -> int:
    url = make_url(settings.database_url)
    if not url.drivername.startswith("sqlite") or not url.database:
        print("只支援 SQLite 檔案資料庫的備份")
        return 1
    db_path = Path(url.database)
    print(f"備份完成：{backup(db_path, db_path.parent / 'backups')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
