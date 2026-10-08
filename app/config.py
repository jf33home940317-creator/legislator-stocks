from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """所有設定都可以用同名（大寫）環境變數或 .env 檔覆蓋。"""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "sqlite:///./data/app.db"
    admin_api_key: str = "change-me"
    # 環境變數要寫成 JSON 陣列，例如 CORS_ORIGINS='["https://a.com"]'
    cors_origins: list[str] = []


settings = Settings()