from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    bot_token: str = Field(default="", alias="BOT_TOKEN")
    admin_ids: set[int] = Field(default_factory=set, alias="ADMIN_IDS")
    default_provider: str = Field(default="gelbooru", alias="DEFAULT_PROVIDER")
    database_path: str = Field(default="data/bot.sqlite3", alias="DATABASE_PATH")
    rate_limit_seconds: int = Field(default=8, alias="RATE_LIMIT_SECONDS")
    daily_limit: int = Field(default=50, alias="DAILY_LIMIT")
    result_limit: int = Field(default=30, alias="RESULT_LIMIT")
    proxy_url: str | None = Field(default=None, alias="PROXY_URL")

    danbooru_base_url: str = Field(default="https://danbooru.donmai.us", alias="DANBOORU_BASE_URL")
    gelbooru_base_url: str = Field(default="https://gelbooru.com", alias="GELBOORU_BASE_URL")
    rule34_base_url: str = Field(default="https://api.rule34.xxx", alias="RULE34_BASE_URL")
    yandere_base_url: str = Field(default="https://yande.re", alias="YANDERE_BASE_URL")
    konachan_base_url: str = Field(default="https://konachan.com", alias="KONACHAN_BASE_URL")
    shimmie_base_url: str = Field(default="", alias="SHIMMIE_BASE_URL")

    @field_validator("admin_ids", mode="before")
    @classmethod
    def parse_admin_ids(cls, value: str | set[int] | list[int]) -> set[int]:
        if isinstance(value, set):
            return value
        if isinstance(value, list):
            return {int(v) for v in value}
        return {int(v.strip()) for v in str(value).split(",") if v.strip()}

    @field_validator("proxy_url", mode="before")
    @classmethod
    def parse_proxy_url(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = str(value).strip()
        return value or None


@lru_cache
def get_settings() -> Settings:
    return Settings()
