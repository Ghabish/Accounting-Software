"""Application settings, read from environment variables or a .env file.

See configuration/.env.example for every option.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="UCF_", env_file=str(BASE_DIR / ".env"), extra="ignore")

    app_name: str = "Universal Cinemas Finance"
    environment: str = "development"  # development | production | test
    database_url: str = "postgresql+psycopg://postgres@localhost:5432/ucfin"
    secret_key: str = "CHANGE-ME-dev-only-secret-key-please-override-0123456789"  # noqa: S105
    access_token_minutes: int = 480
    password_iterations: int = 390_000
    max_failed_logins: int = 5
    lockout_minutes: int = 15
    min_password_length: int = 10
    cors_origins: str = ""  # comma separated; empty = same-origin only
    attachment_dir: str = str(BASE_DIR / "storage" / "attachments")
    max_upload_mb: int = 20
    frontend_dist: str = str(BASE_DIR / "frontend" / "dist")
    duplicate_invoice_warning_days: int = 30
    sql_echo: bool = False
    enable_api_docs: bool = True
    admin_password: str | None = None  # initial administrator password used by scripts.seed
    login_ip_max_failures: int = 20
    login_ip_window_minutes: int = 15

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")


DEFAULT_SECRET = "CHANGE-ME-dev-only-secret-key-please-override-0123456789"


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    if s.environment == "production":
        if s.secret_key == DEFAULT_SECRET or len(s.secret_key) < 32:
            raise RuntimeError("UCF_SECRET_KEY must be set to a random value of at least 32 characters in production")
        if s.is_sqlite:
            raise RuntimeError("Production requires PostgreSQL (UCF_DATABASE_URL)")
    return s
