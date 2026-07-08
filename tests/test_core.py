from __future__ import annotations

import asyncio

import pytest
from aiogram.client.session.aiohttp import AiohttpSession

from app.bot import _aiogram_proxy_url, create_bot
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


@pytest.mark.parametrize("proxy_url", ["socks5://127.0.0.1:1080", "socks5h://127.0.0.1:1080"])
def test_create_bot_uses_aiohttp_session_for_proxy(proxy_url):
    settings = Settings(
        BOT_TOKEN="123:abc",
        ADMIN_IDS="",
        PROXY_URL=proxy_url,
        DEFAULT_PROVIDER="gelbooru",
        DATABASE_PATH=":memory:",
    )
    bot = create_bot(settings)
    try:
        assert isinstance(bot.session, AiohttpSession)
        assert bot.session._proxy == _aiogram_proxy_url(proxy_url)
        assert bot.session._connector_init["host"] == "127.0.0.1"
        assert bot.session._connector_init["port"] == 1080
    finally:
        asyncio.run(bot.session.close())


def test_create_bot_uses_default_session_without_proxy():
    settings = Settings(
        BOT_TOKEN="123:abc",
        ADMIN_IDS="",
        DEFAULT_PROVIDER="gelbooru",
        DATABASE_PATH=":memory:",
    )
    bot = create_bot(settings)
    try:
        assert isinstance(bot.session, AiohttpSession)
        assert bot.session._proxy is None
    finally:
        asyncio.run(bot.session.close())


class FakeProvidersForContext:
    providers = {"gelbooru": object()}

    async def healthcheck_all(self):
        from app.models import ProviderStatus

        return [ProviderStatus("gelbooru", True, 1, "ok")]


class FakeContext:
    db = object()
    providers = FakeProvidersForContext()
    channel = object()


def test_build_dispatcher_initializes_context_before_polling():
    from app.bot import build_dispatcher, clear_context, get_context

    clear_context()
    ctx = FakeContext()
    dp = build_dispatcher(ctx)

    assert dp["ctx"] is ctx
    assert get_context() is ctx
    clear_context()


def test_get_context_does_not_raise_after_startup_setup():
    from app.bot import clear_context, get_context, set_context

    clear_context()
    ctx = FakeContext()
    set_context(ctx)

    assert get_context() is ctx
    clear_context()


def test_main_callbacks_can_access_workflow_context():
    from app.handlers.admin import providers_report

    report = asyncio.run(providers_report(FakeContext()))

    assert "gelbooru: работает" in report


class FakeBot:
    def __init__(self, *, direct_error: Exception | None = None):
        self.calls = []
        self.direct_error = direct_error

    async def send_photo(self, chat_id, photo, **kwargs):
        self.calls.append(("photo", chat_id, photo, kwargs))
        if isinstance(photo, str) and self.direct_error:
            raise self.direct_error
        return {"method": "photo", "photo": photo}

    async def send_document(self, chat_id, document, **kwargs):
        self.calls.append(("document", chat_id, document, kwargs))
        return {"method": "document", "document": document}

    async def send_message(self, chat_id, text):
        self.calls.append(("message", chat_id, text, {}))
        return {"method": "message", "text": text}


class FakeAsyncClient:
    instances = []
    response = None
    error: Exception | None = None

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.requests = []
        FakeAsyncClient.instances.append(self)

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def get(self, url):
        self.requests.append(url)
        if FakeAsyncClient.error:
            raise FakeAsyncClient.error
        return FakeAsyncClient.response


@pytest.fixture(autouse=True)
def reset_fake_async_client():
    FakeAsyncClient.instances = []
    FakeAsyncClient.response = None
    FakeAsyncClient.error = None
    yield


def test_media_sends_buffered_input_file_for_jpeg(monkeypatch):
    from aiogram.types import BufferedInputFile

    from app.services import media

    async def run():
        FakeAsyncClient.response = httpx.Response(
            200,
            content=b"jpeg-bytes",
            headers={"content-type": "image/jpeg"},
            request=httpx.Request("GET", "https://files.example.com/image"),
        )
        monkeypatch.setattr(media.httpx, "AsyncClient", FakeAsyncClient)
        bot = FakeBot()
        post = Post("yandere", "1", "https://files.example.com/image")

        result = await media.send_post(bot, 123, post, settings=Settings(PROXY_URL="http://proxy"))

        assert result["method"] == "photo"
        method, chat_id, photo, kwargs = bot.calls[0]
        assert method == "photo"
        assert chat_id == 123
        assert isinstance(photo, BufferedInputFile)
        assert photo.data == b"jpeg-bytes"
        assert photo.filename == "image.jpg"
        assert kwargs["caption"] == media.post_caption(post)

    import httpx

    asyncio.run(run())


def test_media_falls_back_to_url_if_download_fails(monkeypatch):
    from app.services import media

    async def run():
        FakeAsyncClient.error = httpx.ConnectError("proxy failed")
        monkeypatch.setattr(media.httpx, "AsyncClient", FakeAsyncClient)
        bot = FakeBot()
        post = Post("yandere", "1", "https://files.example.com/a.jpg")

        result = await media.send_post(bot, 123, post, settings=Settings())

        assert result["method"] == "photo"
        assert bot.calls == [
            (
                "photo",
                123,
                "https://files.example.com/a.jpg",
                {"caption": media.post_caption(post), "reply_to_message_id": None},
            )
        ]

    import httpx

    asyncio.run(run())


def test_media_sends_non_image_as_document(monkeypatch):
    from aiogram.types import BufferedInputFile

    from app.services import media

    async def run():
        FakeAsyncClient.response = httpx.Response(
            200,
            content=b"video-bytes",
            headers={"content-type": "video/mp4"},
            request=httpx.Request("GET", "https://files.example.com/clip.mp4"),
        )
        monkeypatch.setattr(media.httpx, "AsyncClient", FakeAsyncClient)
        bot = FakeBot()
        post = Post("yandere", "1", "https://files.example.com/clip.mp4")

        result = await media.send_post(bot, 123, post, settings=Settings())

        assert result["method"] == "document"
        method, _, document, _ = bot.calls[0]
        assert method == "document"
        assert isinstance(document, BufferedInputFile)
        assert document.data == b"video-bytes"
        assert document.filename == "clip.mp4"

    import httpx

    asyncio.run(run())


def test_media_respects_photo_max_size(monkeypatch):
    from app.services import media

    async def run():
        FakeAsyncClient.response = httpx.Response(
            200,
            content=b"x" * (media.PHOTO_MAX_BYTES + 1),
            headers={"content-type": "image/jpeg"},
            request=httpx.Request("GET", "https://files.example.com/large.jpg"),
        )
        monkeypatch.setattr(media.httpx, "AsyncClient", FakeAsyncClient)
        bot = FakeBot()
        post = Post("yandere", "1", "https://files.example.com/large.jpg")

        result = await media.send_post(bot, 123, post, settings=Settings())

        assert result["method"] == "document"
        assert bot.calls[0][0] == "document"

    import httpx

    asyncio.run(run())


def test_media_uses_proxy_url_from_settings(monkeypatch):
    from app.services import media

    async def run():
        FakeAsyncClient.response = httpx.Response(
            200,
            content=b"jpeg-bytes",
            headers={"content-type": "image/jpeg"},
            request=httpx.Request("GET", "https://files.example.com/a.jpg"),
        )
        monkeypatch.setattr(media.httpx, "AsyncClient", FakeAsyncClient)
        proxy_url = "socks5://127.0.0.1:1080"
        post = Post("yandere", "1", "https://files.example.com/a.jpg")

        await media.send_post(FakeBot(), 123, post, settings=Settings(PROXY_URL=proxy_url))

        assert FakeAsyncClient.instances[0].kwargs["proxy"] == proxy_url
        assert FakeAsyncClient.instances[0].kwargs["timeout"] == 20.0
        assert FakeAsyncClient.instances[0].kwargs["headers"]["User-Agent"]
        assert FakeAsyncClient.instances[0].requests == [post.file_url]

    import httpx

    asyncio.run(run())
