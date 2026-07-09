from __future__ import annotations

import asyncio
import logging
import random
import time
from dataclasses import dataclass, field
from typing import Any

LOGGER = logging.getLogger(__name__)
MAX_RANDOM_ATTEMPTS = 15
RANDOM_TITLE = "🦝 Енот Ищейка"
NO_UNIQUE_ART_TEXT = "Пока не нашла новый арт. Попробуйте ещё раз."
INITIAL_EMPTY_ART_TEXT = "Пока не удалось найти арт. Попробуйте позже."
CACHE_WARMING_EMPTY_ART_TEXT = "Енот ещё ищет арты. Попробуйте ещё раз через пару секунд."
FIRST_ART_TEXT = "Это первый просмотренный арт."
SAVE_SUCCESS_NOTIFICATION_TEXT = "Сохранено ⭐"
SAVE_DUPLICATE_NOTIFICATION_TEXT = "Уже в избранном ⭐"
RANDOM_POOL_TARGET_SIZE = 80
RANDOM_POOL_REFILL_THRESHOLD = 30
RANDOM_POOL_MIN_USABLE_SIZE = 5
SEARCH_CACHE_TTL_SECONDS = 30 * 60
SEARCH_CACHE_TARGET_SIZE = 50
PROVIDER_COOLDOWN_SECONDS = 5 * 60
RANDOM_LIVE_MAX_PROVIDERS = 3
RANDOM_LIVE_TIMEOUT_SECONDS = 10
SEARCH_LIVE_CONCURRENCY = 5
SEARCH_LIVE_TIMEOUT_SECONDS = 12


@dataclass(frozen=True)
class Artwork:
    provider_id: str
    post_id: str
    file_url: str
    preview_url: str
    tags: tuple[str, ...]
    rating: str = "safe"
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def unique_key(self) -> tuple[str, str]:
        return (self.provider_id, self.post_id)


@dataclass
class UserGallery:
    history: list[Artwork] = field(default_factory=list)
    current_index: int = -1
    favorites: list[tuple[str, str]] = field(default_factory=list)

    @property
    def current(self) -> Artwork | None:
        if 0 <= self.current_index < len(self.history):
            return self.history[self.current_index]
        return None


class ArtworkProvider:
    id: str
    enabled: bool = True

    async def random_sfw_artwork(self) -> Artwork | None:  # pragma: no cover - interface
        raise NotImplementedError

    async def search(
        self,
        tags: list[str] | tuple[str, ...],
        *,
        mode: str = "sfw",
        limit: int = 20,
        page: int = 0,
    ) -> list[Artwork]:  # pragma: no cover - interface
        raise NotImplementedError


class StaticArtworkProvider(ArtworkProvider):
    def __init__(self, provider_id: str, artworks: list[Artwork], enabled: bool = True) -> None:
        self.id = provider_id
        self._artworks = artworks
        self.enabled = enabled

    async def random_sfw_artwork(self) -> Artwork | None:
        if not self._artworks:
            return None
        return random.choice(self._artworks)

    async def search(
        self,
        tags: list[str] | tuple[str, ...],
        *,
        mode: str = "sfw",
        limit: int = 20,
        page: int = 0,
    ) -> list[Artwork]:
        wanted = set(tags)
        return [art for art in self._artworks if wanted <= set(art.tags)][:limit]


def _static_artwork(index: int, *tags: str) -> Artwork:
    seed = f"raccoon-anime-{index:03d}"
    return Artwork(
        provider_id="local-sfw",
        post_id=f"raccoon-{index:03d}",
        file_url=f"https://picsum.photos/seed/{seed}/900/1200",
        preview_url=f"https://picsum.photos/seed/{seed}/300/400",
        tags=("sfw", "anime", "raccoon", *tags),
        rating="safe",
    )


def _legacy_static_provider() -> StaticArtworkProvider:
    return StaticArtworkProvider("local-sfw", [_static_artwork(i, "tag") for i in range(1, 31)])


def _load_default_providers() -> list[ArtworkProvider]:
    from app.providers import ProviderRegistry

    return list(ProviderRegistry.load().providers)


DEFAULT_PROVIDERS: list[ArtworkProvider] = [_legacy_static_provider()]


def normalize_search_tags(tags: list[str] | tuple[str, ...]) -> list[str]:
    normalized: list[str] = []
    for raw in tags:
        tag = "_".join(str(raw).strip().lower().split())
        if tag and tag not in normalized:
            normalized.append(tag)
    return normalized


def search_cache_key(tags: list[str] | tuple[str, ...]) -> str:
    return ",".join(normalize_search_tags(tags))


@dataclass
class SearchCacheEntry:
    artworks: list[Artwork]
    expires_at: float


class ProviderCacheService:
    def __init__(self, time_func=time.monotonic) -> None:
        self.random_sfw_pool: list[Artwork] = []
        self.search_cache: dict[str, SearchCacheEntry] = {}
        self.cooldowns: dict[str, float] = {}
        self._time = time_func
        self._refill_task: asyncio.Task[None] | None = None
        self._refill_lock = asyncio.Lock()

    def is_on_cooldown(self, provider_id: str) -> bool:
        until = self.cooldowns.get(provider_id)
        if until is None:
            return False
        if until <= self._time():
            self.cooldowns.pop(provider_id, None)
            return False
        LOGGER.info("provider skipped cooldown (%s)", provider_id)
        return True

    def set_cooldown(self, provider_id: str) -> None:
        self.cooldowns[provider_id] = self._time() + PROVIDER_COOLDOWN_SECONDS
        LOGGER.info("provider cooldown set (%s)", provider_id)

    def get_search(self, tags: list[str] | tuple[str, ...]) -> list[Artwork] | None:
        key = search_cache_key(tags)
        entry = self.search_cache.get(key)
        if entry is None or entry.expires_at <= self._time():
            self.search_cache.pop(key, None)
            LOGGER.info("search cache miss (%s)", key)
            return None
        LOGGER.info("search cache hit (%s)", key)
        return list(entry.artworks)

    def put_search(self, tags: list[str] | tuple[str, ...], artworks: list[Artwork]) -> None:
        key = search_cache_key(tags)
        self.search_cache[key] = SearchCacheEntry(
            artworks=list(artworks[:SEARCH_CACHE_TARGET_SIZE]),
            expires_at=self._time() + SEARCH_CACHE_TTL_SECONDS,
        )

    def pop_random_unique(self, seen: set[tuple[str, str]]) -> Artwork | None:
        random.shuffle(self.random_sfw_pool)
        for index, art in enumerate(self.random_sfw_pool):
            if art.unique_key in seen or art.rating != "safe":
                continue
            LOGGER.info("cache random hit")
            return self.random_sfw_pool.pop(index)
        LOGGER.info("cache random miss")
        return None

    def maybe_trigger_refill(self, providers: list[ArtworkProvider]) -> None:
        if len(self.random_sfw_pool) >= RANDOM_POOL_REFILL_THRESHOLD:
            return
        if self._refill_task and not self._refill_task.done():
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        self._refill_task = loop.create_task(self.refill_random_pool(providers))

    async def refill_random_pool(self, providers: list[ArtworkProvider]) -> None:
        async with self._refill_lock:
            LOGGER.info("cache refill started")
            LOGGER.info("preload started")
            seen = {art.unique_key for art in self.random_sfw_pool}
            candidates = [p for p in providers if not self.is_on_cooldown(p.id)]
            random.shuffle(candidates)
            for provider in candidates:
                if len(self.random_sfw_pool) >= RANDOM_POOL_TARGET_SIZE:
                    break
                try:
                    results = await asyncio.wait_for(
                        provider.search([""], mode="sfw", limit=20, page=random.randint(0, 10)),
                        timeout=RANDOM_LIVE_TIMEOUT_SECONDS,
                    )
                except Exception as exc:  # noqa: BLE001
                    LOGGER.info("preload provider failed (%s): %s", provider.id, exc)
                    self.set_cooldown(provider.id)
                    continue
                added = 0
                for art in results:
                    if art.rating != "safe" or art.unique_key in seen:
                        continue
                    self.random_sfw_pool.append(art)
                    seen.add(art.unique_key)
                    added += 1
                    if len(self.random_sfw_pool) >= RANDOM_POOL_TARGET_SIZE:
                        break
                LOGGER.info("preload provider success (%s): %s", provider.id, added)
            LOGGER.info("preload pool size %s", len(self.random_sfw_pool))
            LOGGER.info("cache refill completed")


@dataclass
class SearchSession:
    tags: list[str]
    history: list[Artwork] = field(default_factory=list)
    current_index: int = -1
    page: int = 0
    cached_results: list[Artwork] = field(default_factory=list)
    cached_index: int = 0

    @property
    def current(self) -> Artwork | None:
        if 0 <= self.current_index < len(self.history):
            return self.history[self.current_index]
        return None


class RandomArtService:
    def __init__(self, providers: list[ArtworkProvider] | None = None) -> None:
        self.providers = providers if providers is not None else _load_default_providers()
        self.cache = ProviderCacheService()
        self._users: dict[int, UserGallery] = {}
        self._searches: dict[int, SearchSession] = {}

    def start_preload(self) -> None:
        self.cache.maybe_trigger_refill(self.sfw_providers())

    def gallery(self, user_id: int) -> UserGallery:
        return self._users.setdefault(user_id, UserGallery())

    def sfw_providers(self) -> list[ArtworkProvider]:
        return [
            provider
            for provider in self.providers
            if provider.enabled
            and (
                getattr(provider, "config", None) is None
                or (provider.config.sfw and not provider.config.premium_only)
            )
        ]

    def providers_for_mode(self, mode: str, *, is_premium: bool = False) -> list[ArtworkProvider]:
        if mode == "sfw":
            return self.sfw_providers()
        return [
            p
            for p in self.providers
            if p.enabled
            and getattr(p, "config", None) is not None
            and p.config.nsfw
            and (is_premium or not p.config.premium_only)
        ]

    async def start_search(self, user_id: int, tags: list[str]) -> Artwork | None:
        normalized = normalize_search_tags(tags)
        cached = self.cache.get_search(normalized)
        session = SearchSession(tags=normalized, cached_results=cached or [])
        self._searches[user_id] = session
        LOGGER.info("search session created (%s)", user_id)
        return await self.next_search_artwork(user_id)

    def search_gallery(self, user_id: int) -> SearchSession | None:
        return self._searches.get(user_id)

    def next_search_from_history(self, user_id: int) -> Artwork | None:
        session = self._searches.get(user_id)
        if session is None or session.current_index + 1 >= len(session.history):
            return None
        session.current_index += 1
        return session.current

    def previous_search_artwork(self, user_id: int) -> Artwork | None:
        session = self._searches.get(user_id)
        if session is None or session.current_index <= 0:
            return None
        session.current_index -= 1
        return session.current

    def _append_search_art(self, session: SearchSession, artwork: Artwork) -> Artwork:
        if session.current_index < len(session.history) - 1:
            session.history = session.history[: session.current_index + 1]
        session.history.append(artwork)
        session.current_index = len(session.history) - 1
        return artwork

    async def next_search_artwork(self, user_id: int) -> Artwork | None:
        session = self._searches.get(user_id)
        if session is None:
            return None
        seen = {art.unique_key for art in session.history}
        while session.cached_index < len(session.cached_results):
            art = session.cached_results[session.cached_index]
            session.cached_index += 1
            if art.rating == "safe" and art.unique_key not in seen:
                return self._append_search_art(session, art)
        results = await self._live_search(session.tags, page=session.page)
        session.page += 1
        session.cached_results.extend(results)
        self.cache.put_search(session.tags, session.cached_results)
        for artwork in results:
            if artwork.unique_key not in seen and artwork.rating == "safe":
                session.cached_index += 1
                return self._append_search_art(session, artwork)
        return None

    async def _live_search(self, tags: list[str], *, page: int = 0) -> list[Artwork]:
        providers = [p for p in self.sfw_providers() if not self.cache.is_on_cooldown(p.id)]
        random.shuffle(providers)
        LOGGER.info("search providers queried (%s)", len(providers[:SEARCH_LIVE_CONCURRENCY]))
        semaphore = asyncio.Semaphore(SEARCH_LIVE_CONCURRENCY)
        results: list[Artwork] = []

        async def query(provider: ArtworkProvider) -> list[Artwork]:
            async with semaphore:
                try:
                    found = await provider.search(
                        tags, mode="sfw", limit=SEARCH_CACHE_TARGET_SIZE, page=page
                    )
                except Exception as exc:  # noqa: BLE001
                    LOGGER.warning("search provider failed (%s): %s", provider.id, exc)
                    self.cache.set_cooldown(provider.id)
                    return []
                LOGGER.info("search provider result count (%s): %s", provider.id, len(found))
                return [art for art in found if art.rating == "safe"]

        try:
            batches = await asyncio.wait_for(
                asyncio.gather(*(query(p) for p in providers), return_exceptions=False),
                timeout=SEARCH_LIVE_TIMEOUT_SECONDS,
            )
        except TimeoutError:
            return results[:SEARCH_CACHE_TARGET_SIZE]
        for batch in batches:
            for art in batch:
                if art.unique_key not in {a.unique_key for a in results}:
                    results.append(art)
                    if len(results) >= SEARCH_CACHE_TARGET_SIZE:
                        return results
        return results

    async def next_artwork(self, user_id: int) -> Artwork | None:
        gallery = self.gallery(user_id)
        seen = {art.unique_key for art in gallery.history}
        providers = self.sfw_providers()
        artwork = self.cache.pop_random_unique(seen)
        if artwork is not None:
            self.cache.maybe_trigger_refill(providers)
            return self._append_random(gallery, artwork, user_id)
        self.cache.maybe_trigger_refill(providers)
        return await self._quick_live_random(gallery, seen, providers, user_id)

    def _append_random(self, gallery: UserGallery, artwork: Artwork, user_id: int) -> Artwork:
        if gallery.current_index < len(gallery.history) - 1:
            gallery.history = gallery.history[: gallery.current_index + 1]
        gallery.history.append(artwork)
        gallery.current_index = len(gallery.history) - 1
        LOGGER.info("history push (%s:%s, %s)", *artwork.unique_key, user_id)
        return artwork

    async def _quick_live_random(
        self,
        gallery: UserGallery,
        seen: set[tuple[str, str]],
        providers: list[ArtworkProvider],
        user_id: int,
    ) -> Artwork | None:
        candidates = [p for p in providers if not self.cache.is_on_cooldown(p.id)]
        random.shuffle(candidates)
        attempts = 0
        started_at = time.monotonic()
        while candidates and attempts < RANDOM_LIVE_MAX_PROVIDERS:
            remaining = RANDOM_LIVE_TIMEOUT_SECONDS - (time.monotonic() - started_at)
            if remaining <= 0:
                break
            provider = candidates[attempts % len(candidates)]
            attempts += 1
            try:
                artwork = await asyncio.wait_for(provider.random_sfw_artwork(), timeout=remaining)
            except Exception as exc:  # noqa: BLE001
                LOGGER.warning("provider %s failed: %s", provider.id, exc)
                self.cache.set_cooldown(provider.id)
                continue
            if artwork is None or artwork.rating != "safe" or artwork.unique_key in seen:
                continue
            return self._append_random(gallery, artwork, user_id)
        return None

    def next_from_history(self, user_id: int) -> Artwork | None:
        gallery = self.gallery(user_id)
        if gallery.current_index + 1 >= len(gallery.history):
            return None
        gallery.current_index += 1
        return gallery.history[gallery.current_index]

    def previous_artwork(self, user_id: int) -> Artwork | None:
        gallery = self.gallery(user_id)
        if gallery.current_index <= 0:
            return None
        gallery.current_index -= 1
        return gallery.history[gallery.current_index]

    def save_current(self, user_id: int) -> bool:
        gallery = self.gallery(user_id)
        artwork = gallery.current
        if artwork is None:
            return False
        if artwork.unique_key in gallery.favorites:
            return False
        gallery.favorites.append(artwork.unique_key)
        return True

    def favorite_artworks(self, user_id: int) -> list[Artwork]:
        gallery = self.gallery(user_id)
        by_key = {art.unique_key: art for art in gallery.history}
        return [by_key[key] for key in gallery.favorites if key in by_key]

    def delete_favorite(self, user_id: int, index: int) -> bool:
        gallery = self.gallery(user_id)
        favorites = self.favorite_artworks(user_id)
        if not 0 <= index < len(favorites):
            return False
        key = favorites[index].unique_key
        gallery.favorites = [
            favorite_key for favorite_key in gallery.favorites if favorite_key != key
        ]
        return True


def format_tags_text(artwork: Artwork) -> str:
    tags = ", ".join(artwork.tags)
    return f"{RANDOM_TITLE}\n\n<blockquote expandable>{tags}</blockquote>"
