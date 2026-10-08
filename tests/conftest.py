import pytest
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401  匯入後資料表才會登記到 Base.metadata
from app.db import Base, make_engine


@pytest.fixture
def engine():
    # 記憶體資料庫；StaticPool 讓所有連線共用同一個資料庫
    eng = make_engine("sqlite://", poolclass=StaticPool)
    Base.metadata.create_all(eng)   # 依照 models.py 建立所有資料表
    yield eng
    eng.dispose()


@pytest.fixture
def session_factory(engine):
    return sessionmaker(bind=engine, expire_on_commit=False)


@pytest.fixture
def session(session_factory):
    with session_factory() as s:
        yield s