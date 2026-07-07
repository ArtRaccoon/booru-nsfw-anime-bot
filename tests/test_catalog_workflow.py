import asyncio

import httpx

from app.database import Database
from app.keyboards import catalog_keyboard
from app.providers.catalog import CatalogEntry, parse_catalog
from app.providers.prober import probe_candidate
from app.providers.registry import ProviderRegistry


def texts(markup):
    return [b.text for row in markup.inline_keyboard for b in row]


def test_catalog_keyboard_required_buttons():
    labels = texts(catalog_keyboard())
    for label in [
        "📥 Загрузить каталог",
        "🧪 Проверить все",
        "✅ Доступные",
        "💤 Непроверенные",
        "💥 Недоступные",
        "🔍 Инфо по slug",
        "✅ Включить",
        "🚫 Отключить",
    ]:
        assert label in labels


def test_parse_catalog_deduplicates_and_infers_engine():
    entries = parse_catalog("[Danbooru](https://danbooru.donmai.us) https://danbooru.donmai.us")
    assert len(entries) == 1
    assert entries[0].slug == "danbooru_donmai_us"
    assert entries[0].engine == "danbooru"


def test_candidate_import_status_enable_disable_and_registry(tmp_path):
    async def run():
        db = Database(str(tmp_path / "bot.sqlite3"))
        await db.connect()
        try:
            entry = CatalogEntry(
                slug="extra_danbooru",
                name="Extra",
                base_url="https://extra.test",
                engine="danbooru",
            )
            summary = await db.upsert_provider_candidates([entry])
            assert summary["imported"] == 1
            summary = await db.upsert_provider_candidates(
                [
                    CatalogEntry(
                        slug="extra_danbooru",
                        name="Extra 2",
                        base_url="https://extra.test",
                        engine="danbooru",
                    )
                ]
            )
            assert summary["updated"] == 1
        finally:
            await db.conn.close()

    asyncio.run(run())


def test_candidate_enable_disable_registry(tmp_path):
    async def run():
        db = Database(str(tmp_path / "bot.sqlite3"))
        await db.connect()
        try:
            await db.upsert_provider_candidates(
                [
                    CatalogEntry(
                        "danbooru", "Conflict", "https://candidate.test", engine="danbooru"
                    ),
                    CatalogEntry(
                        "candidate_ok", "Candidate", "https://candidate.test", engine="danbooru"
                    ),
                ]
            )
            await db.update_candidate_probe(
                "candidate_ok",
                type(
                    "R",
                    (),
                    {
                        "availability_status": "available",
                        "http_status": 200,
                        "error": None,
                        "engine": "danbooru",
                    },
                )(),
            )
            assert not await db.set_candidate_enabled("missing", True)
            assert await db.set_candidate_enabled("candidate_ok", True)
            counts = await db.provider_catalog_counts()
            assert counts["available"] == 1
            registry = ProviderRegistry.load()
            await registry.add_enabled_candidates(db)
            try:
                assert registry.configs["danbooru"].base_url != "https://candidate.test"
                assert "candidate_ok" in registry.providers
            finally:
                await registry.close()
            await db.set_candidate_enabled("candidate_ok", False)
            registry = ProviderRegistry.load()
            await registry.add_enabled_candidates(db)
            try:
                assert "candidate_ok" not in registry.providers
            finally:
                await registry.close()
        finally:
            await db.conn.close()

    asyncio.run(run())


def test_prober_classifies_available_for_unknown_fallback():
    async def run():
        def handler(request):
            assert request.url.path == "/posts.json"
            return httpx.Response(200, json=[])

        transport = httpx.MockTransport(handler)
        original = httpx.AsyncClient

        def client_factory(*args, **kwargs):
            kwargs["transport"] = transport
            return original(*args, **kwargs)

        httpx.AsyncClient = client_factory
        try:
            result = await probe_candidate("https://booru.test", "unknown")
        finally:
            httpx.AsyncClient = original
        assert result.availability_status == "available"

    asyncio.run(run())
