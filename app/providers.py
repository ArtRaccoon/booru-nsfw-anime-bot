from __future__ import annotations

import logging
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

from app.config import get_settings
from app.random_art import Artwork

LOGGER = logging.getLogger(__name__)
KNOWN_ENGINES = {"danbooru", "moebooru", "gelbooru_02", "e621", "philomena", "nozomi"}
DEFAULT_TIMEOUT = 8
USER_AGENT = "ArtRaccoonBooruBot/1.0"


@dataclass(frozen=True)
class ProviderConfig:
    id: str
    name: str
    engine: str
    base_url: str
    enabled: bool
    sfw: bool
    nsfw: bool
    premium_only: bool
    priority: int
    timeout_seconds: int = DEFAULT_TIMEOUT


class BooruProvider:
    def __init__(self, config: ProviderConfig) -> None:
        self.config = config
        self.id = config.id
        self.enabled = config.enabled

    async def random_sfw_artwork(self) -> Artwork | None:
        results = await self.search(
            ["rating:safe"], mode="sfw", limit=12, page=random.randint(0, 10)
        )
        return random.choice(results) if results else None

    async def search(
        self,
        tags: list[str] | tuple[str, ...],
        *,
        mode: str = "sfw",
        limit: int = 20,
        page: int = 0,
    ) -> list[Artwork]:
        if self.config.engine == "nozomi":
            return []
        params = self._params(list(tags), mode=mode, limit=limit, page=page)
        headers = {"User-Agent": USER_AGENT} if self.config.engine == "e621" else {}
        try:
            async with httpx.AsyncClient(
                proxy=get_settings().proxy_url,
                timeout=self.config.timeout_seconds,
                headers=headers,
                follow_redirects=True,
            ) as client:
                response = await client.get(self._api_path(), params=params)
                response.raise_for_status()
                data = response.json()
        except Exception as exc:  # noqa: BLE001 - provider failures must never crash handlers
            LOGGER.warning("provider %s failed: %s", self.id, exc)
            return []
        try:
            return self.normalize(data)
        except Exception as exc:  # noqa: BLE001
            LOGGER.warning("provider %s normalization failed: %s", self.id, exc)
            return []

    def _api_path(self) -> str:
        base = self.config.base_url.rstrip("/")
        return {
            "danbooru": f"{base}/posts.json",
            "moebooru": f"{base}/post.json",
            "gelbooru_02": f"{base}/index.php",
            "e621": f"{base}/posts.json",
            "philomena": f"{base}/api/v1/json/search/images",
        }[self.config.engine]

    def _params(self, tags: list[str], *, mode: str, limit: int, page: int) -> dict[str, Any]:
        query_tags = safety_tags(self.config.engine, mode) + tags
        query = " ".join(dict.fromkeys(query_tags))
        if self.config.engine == "danbooru":
            return {"tags": query, "limit": limit, "random": "true"}
        if self.config.engine == "moebooru":
            return {"tags": query, "limit": limit}
        if self.config.engine == "gelbooru_02":
            return {
                "page": "dapi",
                "s": "post",
                "q": "index",
                "json": 1,
                "tags": query,
                "limit": limit,
                "pid": page,
            }
        if self.config.engine == "e621":
            return {"tags": query, "limit": limit}
        if self.config.engine == "philomena":
            return {"q": query, "per_page": limit, "page": max(1, page + 1)}
        return {}

    def normalize(self, data: Any) -> list[Artwork]:
        normalizers = {
            "danbooru": normalize_danbooru,
            "moebooru": normalize_moebooru,
            "gelbooru_02": normalize_gelbooru_02,
            "e621": normalize_e621,
            "philomena": normalize_philomena,
        }
        return normalizers[self.config.engine](self.id, data)


def safety_tags(engine: str, mode: str) -> list[str]:
    if mode != "sfw":
        return []
    return {
        "danbooru": ["rating:safe"],
        "moebooru": ["rating:safe"],
        "gelbooru_02": ["rating:safe"],
        "e621": ["rating:s"],
        "philomena": ["safe", "-explicit"],
    }.get(engine, [])


def _tags(value: Any) -> tuple[str, ...]:
    if isinstance(value, list):
        return tuple(str(tag) for tag in value if tag)
    return tuple(str(value or "").split())


def _rating(value: Any) -> str:
    raw = str(value or "").lower()
    return "safe" if raw in {"s", "safe", "general"} else "explicit"


def _art(
    provider_id: str, post_id: Any, file_url: Any, preview_url: Any, tags: Any, rating: Any
) -> Artwork | None:
    if not post_id or not file_url:
        return None
    return Artwork(
        provider_id=provider_id,
        post_id=str(post_id),
        file_url=str(file_url),
        preview_url=str(preview_url or file_url),
        tags=_tags(tags),
        rating=_rating(rating),
    )


def normalize_danbooru(provider_id: str, data: Any) -> list[Artwork]:
    posts = data if isinstance(data, list) else []
    return [
        art
        for p in posts
        if (
            art := _art(
                provider_id,
                p.get("id"),
                p.get("file_url"),
                p.get("preview_file_url") or p.get("large_file_url"),
                p.get("tag_string"),
                p.get("rating"),
            )
        )
    ]


def normalize_moebooru(provider_id: str, data: Any) -> list[Artwork]:
    posts = data if isinstance(data, list) else []
    return [
        art
        for p in posts
        if (
            art := _art(
                provider_id,
                p.get("id"),
                p.get("file_url"),
                p.get("preview_url") or p.get("sample_url"),
                p.get("tags"),
                p.get("rating"),
            )
        )
    ]


def _gelbooru_posts(data: Any) -> list[dict[str, Any]]:
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        posts = data.get("post", data.get("posts"))
        if isinstance(posts, list):
            return posts
        if isinstance(posts, dict):
            return [posts]
        if "file_url" in data:
            return [data]
    return []


def normalize_gelbooru_02(provider_id: str, data: Any) -> list[Artwork]:
    return [
        art
        for p in _gelbooru_posts(data)
        if (
            art := _art(
                provider_id,
                p.get("id"),
                p.get("file_url"),
                p.get("preview_url") or p.get("sample_url"),
                p.get("tags"),
                p.get("rating"),
            )
        )
    ]


def normalize_e621(provider_id: str, data: Any) -> list[Artwork]:
    posts = data.get("posts", []) if isinstance(data, dict) else []
    artworks: list[Artwork] = []
    for p in posts:
        tag_map = p.get("tags") or {}
        tags: list[str] = []
        for key in ("general", "character", "copyright", "artist", "species"):
            tags.extend(tag_map.get(key) or [])
        file_url = (p.get("file") or {}).get("url")
        preview_url = (p.get("preview") or {}).get("url")
        if art := _art(provider_id, p.get("id"), file_url, preview_url, tags, p.get("rating")):
            artworks.append(art)
    return artworks


def normalize_philomena(provider_id: str, data: Any) -> list[Artwork]:
    images = data.get("images", []) if isinstance(data, dict) else []
    artworks: list[Artwork] = []
    for p in images:
        reps = p.get("representations") or {}
        file_url = reps.get("full") or reps.get("large") or reps.get("medium") or reps.get("thumb")
        rating = "explicit" if {"explicit", "questionable"} & set(p.get("tags") or []) else "safe"
        if art := _art(
            provider_id, p.get("id"), file_url, reps.get("thumb") or file_url, p.get("tags"), rating
        ):
            artworks.append(art)
    return artworks


def _parse_scalar(value: str) -> Any:
    value = value.strip()
    if value.lower() == "true":
        return True
    if value.lower() == "false":
        return False
    try:
        return int(value)
    except ValueError:
        return value.strip("'\"")


def _load_simple_providers_yml(path: Path) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    for raw_line in path.read_text().splitlines():
        line = raw_line.split("#", 1)[0].rstrip()
        stripped = line.strip()
        if not stripped or stripped == "providers:":
            continue
        if stripped.startswith("- "):
            if current:
                items.append(current)
            current = {}
            stripped = stripped[2:].strip()
            if not stripped:
                continue
        if current is None or ":" not in stripped:
            continue
        key, value = stripped.split(":", 1)
        current[key.strip()] = _parse_scalar(value)
    if current:
        items.append(current)
    return items


class ProviderRegistry:
    def __init__(
        self, configs: list[ProviderConfig], providers: list[BooruProvider], unknown: int = 0
    ) -> None:
        self.configs = configs
        self.providers = providers
        self.unknown_engines = unknown

    @classmethod
    def load(cls, path: str | Path = "providers.yml") -> ProviderRegistry:
        file_path = Path(path)
        if not file_path.exists():
            LOGGER.warning("providers.yml missing; provider registry empty")
            return cls([], [], 0)
        items = _load_simple_providers_yml(file_path)
        configs: list[ProviderConfig] = []
        providers: list[BooruProvider] = []
        unknown = 0
        for item in items:
            try:
                config = ProviderConfig(**item)
            except TypeError as exc:
                LOGGER.warning("invalid provider skipped: %s", exc)
                continue
            configs.append(config)
            if config.engine not in KNOWN_ENGINES:
                unknown += 1
                continue
            providers.append(BooruProvider(config))
        providers.sort(key=lambda p: p.config.priority, reverse=True)
        LOGGER.info("Loaded providers: %s", len(configs))
        LOGGER.info("Enabled providers: %s", len([p for p in providers if p.enabled]))
        LOGGER.info("Unknown engines: %s", unknown)
        return cls(configs, providers, unknown)

    def select(self, *, mode: str = "sfw", is_premium: bool = False) -> list[BooruProvider]:
        selected = []
        for provider in self.providers:
            config = provider.config
            if not config.enabled:
                continue
            if mode == "sfw" and (not config.sfw or config.premium_only):
                continue
            if mode == "nsfw" and (not config.nsfw or (config.premium_only and not is_premium)):
                continue
            selected.append(provider)
        return selected
