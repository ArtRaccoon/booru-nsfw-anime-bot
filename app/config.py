from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    bot_token: str = Field("", alias="BOT_TOKEN")
    admin_ids: list[int] = Field(default_factory=list, alias="ADMIN_IDS")
    proxy_url: str | None = Field(None, alias="PROXY_URL")
    default_provider: str = Field("gelbooru", alias="DEFAULT_PROVIDER")
    database_path: str = Field("data/bot.sqlite3", alias="DATABASE_PATH")

    @field_validator("admin_ids", mode="before")
    @classmethod
    def parse_admin_ids(cls, value: object) -> list[int]:
        if value in (None, ""):
            return []
        if isinstance(value, list):
            return [int(v) for v in value]
        return [
            int(part.strip()) for part in str(value).replace(";", ",").split(",") if part.strip()
        ]

    @field_validator("proxy_url", mode="before")
    @classmethod
    def empty_proxy_is_none(cls, value: object) -> str | None:
        return None if value in (None, "") else str(value)

    def ensure_data_dir(self) -> None:
        path = Path(self.database_path)
        if path.parent != Path(""):
            path.parent.mkdir(parents=True, exist_ok=True)

    def is_admin(self, user_id: int | None) -> bool:
        return bool(user_id and user_id in self.admin_ids)


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.ensure_data_dir()
    return settings
