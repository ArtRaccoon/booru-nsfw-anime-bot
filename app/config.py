import logging
from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger("admin")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    bot_token: str = Field(default="", alias="BOT_TOKEN")
    admin_ids: set[int] = Field(default_factory=set, alias="ADMIN_IDS")
    default_provider: str = Field(default="danbooru", alias="DEFAULT_PROVIDER")
    database_path: str = Field(default="data/bot.sqlite3", alias="DATABASE_PATH")
    rate_limit_seconds: int = Field(default=8, alias="RATE_LIMIT_SECONDS")
    daily_limit: int = Field(default=50, alias="DAILY_LIMIT")
    result_limit: int = Field(default=30, alias="RESULT_LIMIT")
    proxy_url: str | None = Field(default=None, alias="PROXY_URL")
    booru_catalog_source_url: str = Field(
        default="https://raw.githubusercontent.com/red-tails/list-of-boorus/master/README.md",
        alias="BOORU_CATALOG_SOURCE_URL",
    )
    booru_catalog_probe_concurrency: int = Field(default=5, alias="BOORU_CATALOG_PROBE_CONCURRENCY")
    booru_catalog_timeout_seconds: int = Field(default=10, alias="BOORU_CATALOG_TIMEOUT_SECONDS")
    booru_user_agent: str = Field(
        default="ArtRaccoonBooruBot/0.1 (+Telegram bot)", alias="BOORU_USER_AGENT"
    )

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
            value = ",".join(str(v) for v in value)
        parsed: set[int] = set()
        for raw in str(value).split(","):
            raw = raw.strip()
            if not raw:
                continue
            try:
                parsed.add(int(raw))
            except ValueError:
                logger.warning("Ignoring invalid ADMIN_IDS value %r", raw)
        return parsed

    @field_validator("proxy_url", mode="before")
    @classmethod
    def parse_proxy_url(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = str(value).strip()
        if not value:
            return None
        if "://" not in value:
            logger.warning("Ignoring invalid PROXY_URL value %r", value)
            return None
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
