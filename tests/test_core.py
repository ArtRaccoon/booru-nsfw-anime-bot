from __future__ import annotations

import asyncio

from app.config import Settings
from app.db import Database
from app.keyboards import admin_menu, main_menu
from app.models import Post
from app.services.providers import ProviderManager


def button_texts(markup):
    return [button.text for row in markup.inline_keyboard for button in row]


def test_config_defaults_and_admin_parse():
    settings = Settings(
        BOT_TOKEN="", ADMIN_IDS="1,2", DEFAULT_PROVIDER="gelbooru", DATABASE_PATH=":memory:"
    )
    assert settings.admin_ids == [1, 2]
    assert settings.proxy_url is None
    assert settings.is_admin(1)


def test_db_migration_idempotent(tmp_path):
    async def run():
        db = Database(str(tmp_path / "bot.sqlite3"))
        await db.migrate()
        await db.migrate()
        row = await db.fetchone("SELECT COUNT(*) AS c FROM channel_settings")
        assert row["c"] == 1

    asyncio.run(run())


class GoodProvider:
    name = "good"

    async def search(self, tags="", page=1, limit=20):
        return [Post("good", "1", "https://example.com/a.jpg")]

    async def healthcheck(self):
        raise AssertionError


class BadProvider(GoodProvider):
    name = "bad"

    async def search(self, tags="", page=1, limit=20):
        raise RuntimeError("broken")


def test_provider_fallback(tmp_path):
    async def run():
        settings = Settings(
            BOT_TOKEN="",
            ADMIN_IDS="",
            DEFAULT_PROVIDER="bad",
            DATABASE_PATH=str(tmp_path / "db.sqlite3"),
        )
        db = Database(settings.database_path)
        await db.migrate()
        manager = ProviderManager(settings, db)
        manager.providers = {"bad": BadProvider(), "good": GoodProvider()}
        await manager.ensure_settings()
        name, posts = await manager.search("x")
        assert name == "good"
        assert posts[0].post_id == "1"

    asyncio.run(run())


def test_channel_settings(tmp_path):
    async def run():
        db = Database(str(tmp_path / "bot.sqlite3"))
        await db.migrate()
        await db.execute(
            "UPDATE channel_settings SET channel_id = ?, enabled = 1 WHERE id = 1", ("@chan",)
        )
        row = await db.fetchone("SELECT * FROM channel_settings WHERE id = 1")
        assert row["channel_id"] == "@chan"
        assert row["enabled"] == 1

    asyncio.run(run())


def test_keyboards_have_no_duplicate_buttons():
    for markup in (main_menu(True), admin_menu()):
        texts = button_texts(markup)
        assert len(texts) == len(set(texts))


def test_admin_check_helper():
    settings = Settings(
        BOT_TOKEN="", ADMIN_IDS="42", DEFAULT_PROVIDER="gelbooru", DATABASE_PATH=":memory:"
    )
    assert settings.is_admin(42)
    assert not settings.is_admin(7)


def test_builtin_providers_exist():
    from app.services.providers import BUILTIN_PROVIDER_CLASSES

    required = {
        "danbooru",
        "safebooru_donmai",
        "yandere",
        "konachan",
        "sakugabooru",
        "gelbooru",
        "rule34",
    }
    assert required <= set(BUILTIN_PROVIDER_CLASSES)
