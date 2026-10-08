from app.config import Settings


def test_default_database_is_sqlite():
    settings = Settings(_env_file=None)
    assert settings.database_url == "sqlite:///./data/app.db"


def test_env_overrides_default(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite:///./other.db")
    monkeypatch.setenv("CORS_ORIGINS", '["https://example.com"]')
    settings = Settings(_env_file=None)
    assert settings.database_url == "sqlite:///./other.db"
    assert settings.cors_origins == ["https://example.com"]
