from alembic import command
from alembic.config import Config
from sqlalchemy import inspect

from app.config import settings
from app.db import Base, make_engine


def test_migrations_create_every_table(tmp_path, monkeypatch):
    url = f"sqlite:///{(tmp_path / 'migrated.db').as_posix()}"
    monkeypatch.setattr(settings, "database_url", url)

    command.upgrade(Config("alembic.ini"), "head")

    tables = set(inspect(make_engine(url)).get_table_names()) - {"alembic_version"}
    assert tables == set(Base.metadata.tables)
