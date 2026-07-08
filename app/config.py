from __future__ import annotations

from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    bot_token: str = Field("", alias="BOT_TOKEN")
    proxy_url: str | None = Field(None, alias="PROXY_URL")

    @field_validator("proxy_url", mode="before")
    @classmethod
    def empty_proxy_is_none(cls, value: object) -> str | None:
        return None if value in (None, "") else str(value)


@lru_cache
def get_settings() -> Settings:
    return Settings()
