from __future__ import annotations

import asyncio

from app.providers import (
    BooruProvider,
    ProviderConfig,
    ProviderRegistry,
    normalize_danbooru,
    normalize_e621,
    normalize_gelbooru_02,
    normalize_moebooru,
    normalize_philomena,
)
from app.random_art import RandomArtService


def config(**overrides):
    data = {
        "id": "p",
        "name": "Provider",
        "engine": "danbooru",
        "base_url": "https://example.test",
        "enabled": True,
        "sfw": True,
        "nsfw": False,
        "premium_only": False,
        "priority": 1,
    }
    data.update(overrides)
    return ProviderConfig(**data)


def test_providers_yml_loads_and_level_1_count():
    registry = ProviderRegistry.load("providers.yml")

    assert len(registry.configs) >= 25
    assert registry.unknown_engines == 0
    assert len(registry.providers) >= 25


def test_unknown_engines_skipped(tmp_path):
    providers_file = tmp_path / "providers.yml"
    providers_file.write_text(
        "providers:\n"
        "  - id: nope\n"
        "    name: Nope\n"
        "    engine: unknown\n"
        "    base_url: https://example.test\n"
        "    enabled: true\n"
        "    sfw: true\n"
        "    nsfw: false\n"
        "    premium_only: false\n"
        "    priority: 1\n"
    )

    registry = ProviderRegistry.load(providers_file)

    assert registry.unknown_engines == 1
    assert registry.providers == []


def test_premium_only_providers_not_selected_for_sfw_random():
    premium = BooruProvider(config(id="premium", sfw=True, nsfw=True, premium_only=True))
    public = BooruProvider(config(id="public", sfw=True, nsfw=False, premium_only=False))
    service = RandomArtService([premium, public])

    assert service.sfw_providers() == [public]


def test_premium_internal_selection_rules():
    premium = BooruProvider(config(id="premium", sfw=False, nsfw=True, premium_only=True))
    public_nsfw = BooruProvider(config(id="public", sfw=True, nsfw=True, premium_only=False))
    service = RandomArtService([premium, public_nsfw])

    assert service.providers_for_mode("nsfw", is_premium=False) == [public_nsfw]
    assert service.providers_for_mode("nsfw", is_premium=True) == [premium, public_nsfw]


def test_danbooru_normalization():
    art = normalize_danbooru(
        "dan",
        [
            {
                "id": 1,
                "file_url": "https://f",
                "preview_file_url": "https://p",
                "tag_string": "a b",
                "rating": "s",
            }
        ],
    )[0]

    assert art.provider_id == "dan"
    assert art.post_id == "1"
    assert art.tags == ("a", "b")
    assert art.rating == "safe"


def test_moebooru_normalization():
    art = normalize_moebooru(
        "moe",
        [
            {
                "id": 2,
                "file_url": "https://f",
                "sample_url": "https://s",
                "tags": "x y",
                "rating": "e",
            }
        ],
    )[0]

    assert art.preview_url == "https://s"
    assert art.rating == "explicit"


def test_gelbooru_list_and_dict_normalization():
    assert (
        normalize_gelbooru_02(
            "g", [{"id": 1, "file_url": "https://f", "tags": "a", "rating": "safe"}]
        )[0].post_id
        == "1"
    )
    assert (
        normalize_gelbooru_02(
            "g", {"post": [{"id": 2, "file_url": "https://f", "tags": "a", "rating": "safe"}]}
        )[0].post_id
        == "2"
    )
    assert (
        normalize_gelbooru_02(
            "g", {"posts": {"id": 3, "file_url": "https://f", "tags": "a", "rating": "safe"}}
        )[0].post_id
        == "3"
    )


def test_e621_normalization():
    art = normalize_e621(
        "e",
        {
            "posts": [
                {
                    "id": 4,
                    "file": {"url": "https://f"},
                    "preview": {"url": "https://p"},
                    "tags": {"general": ["a"], "artist": ["b"]},
                    "rating": "q",
                }
            ]
        },
    )[0]

    assert art.tags == ("a", "b")
    assert art.rating == "explicit"


def test_philomena_normalization():
    art = normalize_philomena(
        "ph",
        {
            "images": [
                {
                    "id": 5,
                    "representations": {"full": "https://f", "thumb": "https://t"},
                    "tags": ["safe", "pony"],
                }
            ]
        },
    )[0]

    assert art.file_url == "https://f"
    assert art.rating == "safe"


def test_provider_failure_returns_empty_list():
    provider = BooruProvider(config(base_url="https://127.0.0.1:1"))

    assert asyncio.run(provider.search(["tag"])) == []


def test_safe_filters_added_per_engine():
    assert (
        BooruProvider(config(engine="danbooru"))._params(
            ["long_hair"], mode="sfw", limit=10, page=0
        )["tags"]
        == "long_hair rating:safe"
    )
    assert (
        BooruProvider(config(engine="moebooru"))._params(
            ["long_hair"], mode="sfw", limit=10, page=0
        )["tags"]
        == "long_hair rating:safe"
    )
    assert (
        BooruProvider(config(engine="gelbooru_02"))._params(
            ["long_hair"], mode="sfw", limit=10, page=0
        )["tags"]
        == "long_hair rating:safe"
    )
    assert (
        BooruProvider(config(engine="e621"))._params(["long_hair"], mode="sfw", limit=10, page=0)[
            "tags"
        ]
        == "long_hair rating:s"
    )
    assert (
        "explicit"
        in BooruProvider(config(engine="philomena"))._params(
            ["long_hair"], mode="sfw", limit=10, page=0
        )["q"]
    )


def test_search_params_do_not_force_random_order():
    params = BooruProvider(config(engine="danbooru"))._params(
        ["sunset"], mode="sfw", limit=10, page=0
    )

    assert params == {"tags": "sunset rating:safe", "limit": 10}
