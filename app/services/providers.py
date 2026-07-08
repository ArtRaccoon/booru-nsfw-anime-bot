from __future__ import annotations

import asyncio

from app.config import Settings
from app.db import Database
from app.models import Post, ProviderStatus
from app.providers.base import Provider
from app.providers.danbooru import DanbooruProvider, SafebooruDonmaiProvider
from app.providers.gelbooru import GelbooruProvider
from app.providers.moebooru import KonachanProvider, SakugabooruProvider, YandereProvider
from app.providers.rule34 import Rule34Provider

BUILTIN_PROVIDER_CLASSES: dict[str, type[Provider]] = {
    "danbooru": DanbooruProvider,
    "safebooru_donmai": SafebooruDonmaiProvider,
    "yandere": YandereProvider,
    "konachan": KonachanProvider,
    "sakugabooru": SakugabooruProvider,
    "gelbooru": GelbooruProvider,
    "rule34": Rule34Provider,
}


class ProviderManager:
    def __init__(self, settings: Settings, db: Database):
        self.settings = settings
        self.db = db
        self.providers = {
            name: cls(settings.proxy_url) for name, cls in BUILTIN_PROVIDER_CLASSES.items()
        }

    async def ensure_settings(self) -> None:
        for name in self.providers:
            await self.db.execute(
                "INSERT OR IGNORE INTO provider_settings(provider, enabled) VALUES (?, 1)", (name,)
            )

    async def enabled_names(self) -> list[str]:
        await self.ensure_settings()
        rows = await self.db.fetchall("SELECT provider FROM provider_settings WHERE enabled = 1")
        names = [r["provider"] for r in rows if r["provider"] in self.providers]
        return names or list(self.providers)

    async def set_enabled(self, name: str, enabled: bool) -> None:
        await self.db.execute(
            "INSERT OR REPLACE INTO provider_settings(provider, enabled) VALUES (?, ?)",
            (name, int(enabled)),
        )

    async def search(
        self,
        tags: str,
        provider_name: str | None = None,
        page: int = 1,
        limit: int = 20,
        auto: bool = True,
    ) -> tuple[str, list[Post]]:
        names = [provider_name] if provider_name and not auto else []
        names += [self.settings.default_provider, *(await self.enabled_names())]
        seen = set()
        for name in [n for n in names if n and not (n in seen or seen.add(n))]:
            provider = self.providers.get(name)
            if not provider:
                continue
            try:
                posts = await provider.search(tags, page, limit)
            except Exception:  # noqa: BLE001
                posts = []
            if posts:
                return name, posts
        return "", []

    async def random(
        self, tags: str = "", provider_name: str | None = None, auto: bool = True
    ) -> Post | None:
        _, posts = await self.search(tags, provider_name, 1, 30, auto)
        return posts[0] if posts else None

    async def healthcheck_all(self) -> list[ProviderStatus]:
        return await asyncio.gather(*(p.healthcheck() for p in self.providers.values()))
