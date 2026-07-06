import asyncio

import httpx

from app.handlers.providers import format_provider_info
from app.models import BooruPost
from app.providers.base import BaseProvider
from app.providers.engines.danbooru import DanbooruProvider
from app.providers.engines.gelbooru import GelbooruProvider
from app.providers.registry import ProviderRegistry, engine_class, fallback_search


def test_load_providers_yml():
    registry = ProviderRegistry.load()
    assert "danbooru" in registry.configs
    assert "safebooru_org" in registry.configs
    assert len(registry.configs) > 40


def test_build_correct_engine_adapter_by_engine_name():
    assert engine_class("danbooru") is DanbooruProvider
    assert engine_class("gelbooru_v02") is GelbooruProvider


def test_disabled_providers_are_not_used_by_default():
    registry = ProviderRegistry.load()
    assert "e621" in registry.configs
    assert "e621" not in registry.providers
    assert "rule34" in registry.providers


class ErrorProvider(BaseProvider):
    name = "error"

    async def search(self, tags, limit, page):
        return []

    def normalize_post(self, raw):
        raise NotImplementedError


class GoodProvider(BaseProvider):
    name = "good"

    async def search(self, tags, limit, page):
        return [BooruPost(provider=self.name, post_id="1", file_url="https://x/y.jpg")]

    def normalize_post(self, raw):
        raise NotImplementedError


def test_fallback_moves_to_next_provider():
    async def run():
        bad = ErrorProvider("https://x")
        good = GoodProvider("https://x")
        provider, posts = await fallback_search({"bad": bad, "good": good}, "a", 1, 1)
        assert provider.name == "good"
        assert posts[0].post_id == "1"
        await bad.close()
        await good.close()

    asyncio.run(run())


def test_provider_http_errors_do_not_crash_bot():
    async def run():
        def handler(request):
            return httpx.Response(401, json={"error": "unauthorized"})

        provider = GelbooruProvider("https://gelbooru.test")
        await provider.client.aclose()
        provider.client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        assert await provider.search("tag", 1, 1) == []
        await provider.close()

    asyncio.run(run())


def test_provider_info_command_displays_metadata():
    registry = ProviderRegistry.load()
    text = format_provider_info(registry.configs["danbooru"], True)
    assert "Engine: danbooru" in text
    assert "Category: anime_nsfw" in text


def test_default_provider_falls_back_to_first_enabled_provider():
    registry = ProviderRegistry.load()
    try:
        assert registry.select_default("missing-provider") == registry.enabled_slugs()[0]
    finally:
        asyncio.run(registry.close())


def test_unknown_enabled_engine_does_not_crash_startup():
    base = ProviderRegistry.load()
    danbooru_cfg = base.configs["danbooru"]
    cfg_cls = type(danbooru_cfg)
    asyncio.run(base.close())
    registry = ProviderRegistry(
        [
            danbooru_cfg,
            cfg_cls(
                name="Unknown",
                slug="unknown_enabled",
                engine="new_engine",
                base_url="https://example.com",
                enabled_by_default=True,
            ),
        ]
    )
    try:
        assert "danbooru" in registry.providers
        assert "unknown_enabled" not in registry.providers
    finally:
        asyncio.run(registry.close())
