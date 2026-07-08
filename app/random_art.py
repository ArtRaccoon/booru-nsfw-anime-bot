from __future__ import annotations

import logging
import random
from dataclasses import dataclass, field
from typing import Any

LOGGER = logging.getLogger(__name__)
MAX_RANDOM_ATTEMPTS = 15
RANDOM_TITLE = "🦝 Енот Ищейка"
NO_UNIQUE_ART_TEXT = "Не удалось найти новый арт. Попробуйте ещё раз."
FIRST_ART_TEXT = "Это первый просмотренный арт."
ALREADY_SAVED_TEXT = "Этот арт уже сохранён ⭐"


@dataclass(frozen=True)
class Artwork:
    provider_id: str
    post_id: str
    file_url: str
    preview_url: str
    tags: tuple[str, ...]
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def unique_key(self) -> tuple[str, str]:
        return (self.provider_id, self.post_id)


@dataclass
class UserGallery:
    history: list[Artwork] = field(default_factory=list)
    current_index: int = -1
    favorites: set[tuple[str, str]] = field(default_factory=set)

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


class StaticArtworkProvider(ArtworkProvider):
    def __init__(self, provider_id: str, artworks: list[Artwork], enabled: bool = True) -> None:
        self.id = provider_id
        self._artworks = artworks
        self.enabled = enabled

    async def random_sfw_artwork(self) -> Artwork | None:
        if not self._artworks:
            return None
        return random.choice(self._artworks)


DEFAULT_PROVIDERS: list[ArtworkProvider] = [
    StaticArtworkProvider(
        "local-sfw",
        [
            Artwork(
                provider_id="local-sfw",
                post_id="raccoon-001",
                file_url="https://picsum.photos/seed/raccoon-anime-001/900/1200",
                preview_url="https://picsum.photos/seed/raccoon-anime-001/300/400",
                tags=("sfw", "anime", "raccoon", "girl", "forest", "cute"),
                metadata={"rating": "safe"},
            ),
            Artwork(
                provider_id="local-sfw",
                post_id="raccoon-002",
                file_url="https://picsum.photos/seed/raccoon-anime-002/900/1200",
                preview_url="https://picsum.photos/seed/raccoon-anime-002/300/400",
                tags=("sfw", "anime", "raccoon", "night", "stars", "hoodie"),
                metadata={"rating": "safe"},
            ),
            Artwork(
                provider_id="local-sfw",
                post_id="raccoon-003",
                file_url="https://picsum.photos/seed/raccoon-anime-003/900/1200",
                preview_url="https://picsum.photos/seed/raccoon-anime-003/300/400",
                tags=("sfw", "anime", "raccoon", "cafe", "warm", "smile"),
                metadata={"rating": "safe"},
            ),
        ],
    )
]


class RandomArtService:
    def __init__(self, providers: list[ArtworkProvider] | None = None) -> None:
        self.providers = providers if providers is not None else DEFAULT_PROVIDERS
        self._users: dict[int, UserGallery] = {}

    def gallery(self, user_id: int) -> UserGallery:
        return self._users.setdefault(user_id, UserGallery())

    async def next_artwork(self, user_id: int) -> Artwork | None:
        LOGGER.info("random requested (%s)", user_id)
        gallery = self.gallery(user_id)
        seen = {art.unique_key for art in gallery.history}
        enabled = [provider for provider in self.providers if provider.enabled]
        if not enabled:
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
        return None

    def previous_artwork(self, user_id: int) -> Artwork | None:
        gallery = self.gallery(user_id)
        if gallery.current_index <= 0:
            return None
        gallery.current_index -= 1
        artwork = gallery.history[gallery.current_index]
        LOGGER.info("history previous (%s:%s, %s)", *artwork.unique_key, user_id)
        return artwork

    def save_current(self, user_id: int) -> bool:
        gallery = self.gallery(user_id)
        artwork = gallery.current
        if artwork is None:
            return False
        if artwork.unique_key in gallery.favorites:
            LOGGER.info("favorite duplicate (%s:%s, %s)", *artwork.unique_key, user_id)
            return False
        gallery.favorites.add(artwork.unique_key)
        LOGGER.info("favorite added (%s:%s, %s)", *artwork.unique_key, user_id)
        return True


def format_tags_text(artwork: Artwork) -> str:
    tags = ", ".join(artwork.tags)
    return f"{RANDOM_TITLE}\n\n<blockquote expandable>{tags}</blockquote>"
