from pathlib import Path

from sqlalchemy import MetaData, create_engine, event
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import settings

# 約束（規則）的命名方式。規則有固定的名字，以後 Alembic 才能找到它、修改它
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


# ① 所有資料表的共同祖先
class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


# ② 建立資料庫連線
def make_engine(url: str, **kwargs) -> Engine:
    is_sqlite = url.startswith("sqlite")

    if is_sqlite:
        # FastAPI 會用多個執行緒同時處理請求，要允許共用連線
        kwargs.setdefault("connect_args", {"check_same_thread": False})
        # 從網址取出資料庫檔案的路徑，例如 ./data/app.db
        database = make_url(url).database
        # 如果是檔案（不是記憶體資料庫），先把資料夾建好
        if database and database != ":memory:":
            Path(database).parent.mkdir(parents=True, exist_ok=True)

    engine = create_engine(url, **kwargs)

    if is_sqlite:
        @event.listens_for(engine, "connect")
        def _sqlite_pragmas(dbapi_conn, _record):
            cursor = dbapi_conn.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")                     # 打開外鍵檢查
            cursor.execute("PRAGMA journal_mode=WAL")  # 寫入時仍可同時讀取
            cursor.close()

    return engine


# ③ 全專案共用的連線，以及產生 session 的工具
engine = make_engine(settings.database_url)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)