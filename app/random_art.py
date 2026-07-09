from __future__ import annotations

import logging
import random
from dataclasses import dataclass, field
from typing import Any

LOGGER = logging.getLogger(__name__)
MAX_RANDOM_ATTEMPTS = 15
RANDOM_TITLE = "🦝 Енот Ищейка"
NO_UNIQUE_ART_TEXT = "Пока не нашла новый арт. Попробуйте ещё раз."
INITIAL_EMPTY_ART_TEXT = "Пока не удалось найти арт. Попробуйте позже."
FIRST_ART_TEXT = "Это первый просмотренный арт."
SAVE_SUCCESS_NOTIFICATION_TEXT = "Сохранено ⭐"
SAVE_DUPLICATE_NOTIFICATION_TEXT = "Уже в избранном ⭐"


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


@dataclass
class SearchSession:
    tags: list[str]
    history: list[Artwork] = field(default_factory=list)
    current_index: int = -1
    page: int = 0

    @property
    def current(self) -> Artwork | None:
        if 0 <= self.current_index < len(self.history):
            return self.history[self.current_index]
        return None


class RandomArtService:
    def __init__(self, providers: list[ArtworkProvider] | None = None) -> None:
        self.providers = providers if providers is not None else _load_default_providers()
        self._users: dict[int, UserGallery] = {}
        self._searches: dict[int, SearchSession] = {}

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
            provider
            for provider in self.providers
            if provider.enabled
            and getattr(provider, "config", None) is not None
            and provider.config.nsfw
            and (is_premium or not provider.config.premium_only)
        ]

    async def start_search(self, user_id: int, tags: list[str]) -> Artwork | None:
        self._searches[user_id] = SearchSession(tags=tags)
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

    async def next_search_artwork(self, user_id: int) -> Artwork | None:
        session = self._searches.get(user_id)
        if session is None:
            return None
        seen = {art.unique_key for art in session.history}
        providers = self.sfw_providers()
        random.shuffle(providers)
        for provider in providers:
            results = await provider.search(session.tags, mode="sfw", limit=20, page=session.page)
            for artwork in results:
                if artwork.unique_key in seen or artwork.rating != "safe":
                    continue
                if session.current_index < len(session.history) - 1:
                    session.history = session.history[: session.current_index + 1]
                session.history.append(artwork)
                session.current_index = len(session.history) - 1
                return artwork
        session.page += 1
        return None

    async def next_artwork(self, user_id: int) -> Artwork | None:
        LOGGER.info("fetching new art at end (%s)", user_id)
        gallery = self.gallery(user_id)
        seen = {art.unique_key for art in gallery.history}
        enabled = self.sfw_providers()
        if not enabled:
            LOGGER.info("no unique art available, keeping current item (%s)", user_id)
            return None

        for _ in range(MAX_RANDOM_ATTEMPTS):
            provider = random.choice(enabled)
            LOGGER.info("provider selected (%s, %s)", provider.id, user_id)
            artwork = await provider.random_sfw_artwork()
            if artwork is None:
                continue
            if artwork.unique_key in seen:
                LOGGER.info("duplicate skipped (%s:%s, %s)", *artwork.unique_key, user_id)
                continue
            if gallery.current_index < len(gallery.history) - 1:
                gallery.history = gallery.history[: gallery.current_index + 1]
            gallery.history.append(artwork)
            gallery.current_index = len(gallery.history) - 1
            LOGGER.info("history push (%s:%s, %s)", *artwork.unique_key, user_id)
            return artwork
        LOGGER.info("no unique art available, keeping current item (%s)", user_id)
        return None

    def next_from_history(self, user_id: int) -> Artwork | None:
        gallery = self.gallery(user_id)
        if gallery.current_index + 1 >= len(gallery.history):
            return None
        from_index = gallery.current_index
        gallery.current_index += 1
        artwork = gallery.history[gallery.current_index]
        LOGGER.info(
            "history forward existing from %s to %s (%s)",
            from_index,
            gallery.current_index,
            user_id,
        )
        return artwork

    def previous_artwork(self, user_id: int) -> Artwork | None:
        gallery = self.gallery(user_id)
        if gallery.current_index <= 0:
            return None
        from_index = gallery.current_index
        gallery.current_index -= 1
        artwork = gallery.history[gallery.current_index]
        LOGGER.info(
            "history previous from %s to %s (%s)", from_index, gallery.current_index, user_id
        )
        return artwork

    def save_current(self, user_id: int) -> bool:
        gallery = self.gallery(user_id)
        artwork = gallery.current
        if artwork is None:
            return False
        if artwork.unique_key in gallery.favorites:
            LOGGER.info("favorite duplicate (%s:%s, %s)", *artwork.unique_key, user_id)
            return False
        gallery.favorites.append(artwork.unique_key)
        LOGGER.info("favorite added (%s:%s, %s)", *artwork.unique_key, user_id)
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
        LOGGER.info("favorite removed (%s:%s, %s)", *key, user_id)
        return True


def format_tags_text(artwork: Artwork) -> str:
    tags = ", ".join(artwork.tags)
    return f"{RANDOM_TITLE}\n\n<blockquote expandable>{tags}</blockquote>"
