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
ALREADY_SAVED_TEXT = "Этот арт уже сохранён ⭐"


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


DEFAULT_PROVIDERS: list[ArtworkProvider] = [
    StaticArtworkProvider(
        "local-sfw",
        [
            _static_artwork(1, "girl", "forest", "cute"),
            _static_artwork(2, "night", "stars", "hoodie"),
            _static_artwork(3, "cafe", "warm", "smile"),
            _static_artwork(4, "library", "books", "cozy"),
            _static_artwork(5, "garden", "flowers", "spring"),
            _static_artwork(6, "beach", "summer", "sunny"),
            _static_artwork(7, "city", "rain", "umbrella"),
            _static_artwork(8, "school", "uniform", "day"),
            _static_artwork(9, "festival", "lanterns", "kimono"),
            _static_artwork(10, "mountain", "snow", "scarf"),
            _static_artwork(11, "river", "bridge", "peaceful"),
            _static_artwork(12, "bakery", "pastry", "sweet"),
            _static_artwork(13, "train", "travel", "window"),
            _static_artwork(14, "park", "autumn", "leaves"),
            _static_artwork(15, "studio", "paint", "artist"),
            _static_artwork(16, "shrine", "torii", "calm"),
            _static_artwork(17, "meadow", "butterflies", "soft"),
            _static_artwork(18, "kitchen", "tea", "morning"),
            _static_artwork(19, "rooftop", "sunset", "breeze"),
            _static_artwork(20, "aquarium", "fish", "blue"),
            _static_artwork(21, "museum", "history", "quiet"),
            _static_artwork(22, "camp", "fire", "friends"),
            _static_artwork(23, "greenhouse", "plants", "fresh"),
            _static_artwork(24, "arcade", "games", "neon"),
            _static_artwork(25, "harbor", "boats", "clouds"),
            _static_artwork(26, "observatory", "moon", "telescope"),
            _static_artwork(27, "market", "fruit", "colorful"),
            _static_artwork(28, "castle", "fantasy", "path"),
            _static_artwork(29, "waterfall", "mist", "nature"),
            _static_artwork(30, "bookstore", "coffee", "relaxed"),
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
        LOGGER.info("fetching new art at end (%s)", user_id)
        gallery = self.gallery(user_id)
        seen = {art.unique_key for art in gallery.history}
        enabled = [provider for provider in self.providers if provider.enabled]
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
        gallery.favorites.add(artwork.unique_key)
        LOGGER.info("favorite added (%s:%s, %s)", *artwork.unique_key, user_id)
        return True


def format_tags_text(artwork: Artwork) -> str:
    tags = ", ".join(artwork.tags)
    return f"{RANDOM_TITLE}\n\n<blockquote expandable>{tags}</blockquote>"
