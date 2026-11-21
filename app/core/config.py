from functools import lru_cache
from pathlib import Path
from secrets import token_urlsafe

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import URL

PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env", env_file_encoding="utf-8", extra="ignore"
    )

    app_name: str = "Ping! Messenger"
    sqlite_db_path: str = "msnmessenger_reborn.db"
    jwt_secret_key: SecretStr = Field(default_factory=lambda: SecretStr(token_urlsafe(48)))
    access_token_expire_minutes: int = Field(default=1440, ge=1)
    cors_origins: str = "http://127.0.0.1:8000,http://localhost:8000"
    max_upload_mb: int = Field(default=50, ge=1, le=500)
    upload_dir: str = "uploads"

    @field_validator("jwt_secret_key")
    @classmethod
    def replace_example_secret(cls, value: SecretStr) -> SecretStr:
        if value.get_secret_value() in ("", "REPLACE_WITH_YOUR_OWN_RANDOM_SECRET_48_CHARS_OR_LONGER"):
            return SecretStr(token_urlsafe(48))
        return value

    @property
    def sqlite_path(self) -> Path:
        path = Path(self.sqlite_db_path).expanduser()
        return (path if path.is_absolute() else PROJECT_ROOT / path).resolve()

    @property
    def database_url(self) -> URL:
        return URL.create(drivername="sqlite+pysqlite", database=str(self.sqlite_path))

    @property
    def cors_origin_list(self) -> list[str]:
        return [value.strip() for value in self.cors_origins.split(",") if value.strip()]

    @property
    def upload_path(self) -> Path:
        path = Path(self.upload_dir)
        return (path if path.is_absolute() else PROJECT_ROOT / path).resolve()


@lru_cache
def get_settings() -> Settings:
    return Settings()
