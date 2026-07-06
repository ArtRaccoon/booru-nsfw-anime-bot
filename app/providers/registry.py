from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.providers.base import BaseProvider
from app.providers.engines.danbooru import DanbooruOldProvider, DanbooruProvider
from app.providers.engines.gelbooru import GelbooruProvider
from app.providers.engines.moebooru import MoebooruProvider
from app.providers.engines.philomena import PhilomenaProvider
from app.providers.engines.shimmie import ShimmieProvider
from app.providers.engines.szurubooru import SzurubooruProvider

CONFIG_PATH = Path(__file__).with_name("providers.yml")
DISABLED_ENGINES = {"unknown", "custom", "no_api"}


@dataclass(frozen=True)
class ProviderConfig:
    name: str
    slug: str
    engine: str
    base_url: str
    api_url: str | None = None
    sfw_status: str = "unknown"
    category: str = "unknown"
    enabled_by_default: bool = False
    notes: str = ""
    requires_auth: bool = False
    broken: bool = False
    anime_relevant: bool = False

    @property
    def selectable(self) -> bool:
        return (
            self.enabled_by_default
            and not self.requires_auth
            and not self.broken
            and self.engine not in DISABLED_ENGINES
        )


class ProviderRegistry:
    def __init__(self, configs: list[ProviderConfig], proxy_url: str | None = None) -> None:
        self.configs = {c.slug: c for c in configs}
        self.proxy_url = proxy_url
        self.providers = self._build_enabled()

    @classmethod
    def load(cls, path: Path = CONFIG_PATH, proxy_url: str | None = None) -> ProviderRegistry:
        data = load_provider_yaml(path)
        configs = [ProviderConfig(**item) for item in data]
        return cls(configs, proxy_url=proxy_url)

    def _build_enabled(self) -> dict[str, BaseProvider]:
        return {
            slug: self.build_provider(cfg) for slug, cfg in self.configs.items() if cfg.selectable
        }

    def build_provider(self, cfg_or_slug: ProviderConfig | str) -> BaseProvider:
        cfg = self.configs[cfg_or_slug] if isinstance(cfg_or_slug, str) else cfg_or_slug
        cls = engine_class(cfg.engine)
        return cls(cfg.base_url, name=cfg.slug, api_url=cfg.api_url, proxy_url=self.proxy_url)

    def enable(self, slug: str) -> bool:
        cfg = self.configs.get(slug)
        if not cfg or cfg.engine in DISABLED_ENGINES or cfg.requires_auth or cfg.broken:
            return False
        self.providers[slug] = self.build_provider(cfg)
        return True

    async def disable(self, slug: str) -> bool:
        provider = self.providers.pop(slug, None)
        if provider:
            await provider.close()
            return True
        return slug in self.configs

    async def reload(self) -> None:
        for provider in self.providers.values():
            await provider.close()
        fresh = self.load(proxy_url=self.proxy_url)
        self.configs = fresh.configs
        self.providers = fresh.providers

    def enabled_slugs(self) -> list[str]:
        return list(self.providers)


def engine_class(engine: str) -> type[BaseProvider]:
    engines: dict[str, type[BaseProvider]] = {
        "danbooru": DanbooruProvider,
        "danbooru_old": DanbooruOldProvider,
        "gelbooru_v02": GelbooruProvider,
        "gelbooru_v01": GelbooruProvider,
        "moebooru": MoebooruProvider,
        "shimmie": ShimmieProvider,
        "philomena": PhilomenaProvider,
        "szurubooru": SzurubooruProvider,
    }
    if engine not in engines:
        raise ValueError(f"No adapter for provider engine {engine!r}")
    return engines[engine]


async def fallback_search(
    providers: dict[str, BaseProvider], tags: str, limit: int, page: int
) -> tuple[BaseProvider | None, list[Any]]:
    for provider in providers.values():
        try:
            posts = await provider.search(tags, limit, page)
        except Exception:
            posts = []
        if posts:
            return provider, posts
    return None, []


def load_provider_yaml(path: Path) -> list[dict[str, Any]]:
    providers: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    for raw_line in path.read_text().splitlines():
        line = raw_line.rstrip()
        if not line.strip() or line.strip() == "providers:":
            continue
        stripped = line.strip()
        if stripped.startswith("- "):
            if current:
                providers.append(current)
            current = {}
            stripped = stripped[2:]
            if not stripped:
                continue
        if current is None or ":" not in stripped:
            continue
        key, value = stripped.split(":", 1)
        value = value.strip()
        if value == "null":
            parsed: Any = None
        elif value in {"true", "false"}:
            parsed = value == "true"
        elif len(value) >= 2 and value[0] == value[-1] == '"':
            parsed = value[1:-1]
        else:
            parsed = value
        current[key] = parsed
    if current:
        providers.append(current)
    return providers
