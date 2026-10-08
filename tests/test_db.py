from app.db import make_engine


def test_foreign_keys_are_enabled():
    engine = make_engine("sqlite://")
    with engine.connect() as conn:
        result = conn.exec_driver_sql("PRAGMA foreign_keys").scalar()
    assert result == 1


def test_creates_folder_for_database_file(tmp_path):
    db_file = tmp_path / "new_folder" / "app.db"
    make_engine(f"sqlite:///{db_file.as_posix()}")
    assert db_file.parent.exists()