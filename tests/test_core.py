from __future__ import annotations

import asyncio
from io import BytesIO

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
    def __init__(
        self, *, direct_error: Exception | None = None, photo_error: Exception | None = None
    ):
        self.calls = []
        self.direct_error = direct_error
        self.photo_error = photo_error

    async def send_photo(self, chat_id, photo, **kwargs):
        self.calls.append(("photo", chat_id, photo, kwargs))
        if isinstance(photo, str) and self.direct_error:
            raise self.direct_error
        if not isinstance(photo, str) and self.photo_error:
            raise self.photo_error
        return {"method": "photo", "photo": photo}

    async def send_document(self, chat_id, document, **kwargs):
        self.calls.append(("document", chat_id, document, kwargs))
        return {"method": "document", "document": document}

    async def send_message(self, chat_id, text):
        self.calls.append(("message", chat_id, text, {}))
        return {"method": "message", "text": text}


def make_image_bytes(mode="RGB", size=(10, 10), image_format="PNG", color=None):
    from PIL import Image

    if color is None:
        color = (255, 0, 0, 128) if mode == "RGBA" else (255, 0, 0)
    image = Image.new(mode, size, color)
    output = BytesIO()
    image.save(output, format=image_format)
    return output.getvalue()


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
            content=make_image_bytes(image_format="JPEG"),
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
        assert photo.data.startswith(b"\xff\xd8")
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
            content=make_image_bytes(size=(5000, 3000), image_format="JPEG"),
            headers={"content-type": "image/jpeg"},
            request=httpx.Request("GET", "https://files.example.com/large.jpg"),
        )
        monkeypatch.setattr(media.httpx, "AsyncClient", FakeAsyncClient)
        bot = FakeBot()
        post = Post("yandere", "1", "https://files.example.com/large.jpg")

        result = await media.send_post(bot, 123, post, settings=Settings())

        assert result["method"] == "photo"
        method, _, photo, _ = bot.calls[0]
        assert method == "photo"
        assert photo.data.startswith(b"\xff\xd8")

        from PIL import Image

        with Image.open(BytesIO(photo.data)) as normalized:
            assert max(normalized.size) <= media.PHOTO_MAX_SIDE
            assert sum(normalized.size) <= media.PHOTO_MAX_DIMENSIONS_SUM

    import httpx

    asyncio.run(run())


def test_media_converts_rgba_image_to_jpeg(monkeypatch):
    from aiogram.types import BufferedInputFile
    from PIL import Image

    from app.services import media

    async def run():
        FakeAsyncClient.response = httpx.Response(
            200,
            content=make_image_bytes(mode="RGBA", image_format="PNG"),
            headers={"content-type": "image/png"},
            request=httpx.Request("GET", "https://files.example.com/transparent.png"),
        )
        monkeypatch.setattr(media.httpx, "AsyncClient", FakeAsyncClient)
        bot = FakeBot()
        post = Post("yandere", "1", "https://files.example.com/transparent.png")

        result = await media.send_post(bot, 123, post, settings=Settings())

        assert result["method"] == "photo"
        method, _, photo, _ = bot.calls[0]
        assert method == "photo"
        assert isinstance(photo, BufferedInputFile)
        assert photo.filename == "transparent.jpg"
        with Image.open(BytesIO(photo.data)) as normalized:
            assert normalized.format == "JPEG"
            assert normalized.mode == "RGB"

    import httpx

    asyncio.run(run())


def test_media_invalid_image_falls_back_to_buffered_document(monkeypatch):
    from aiogram.types import BufferedInputFile

    from app.services import media

    async def run():
        FakeAsyncClient.response = httpx.Response(
            200,
            content=b"not an image",
            headers={"content-type": "image/jpeg"},
            request=httpx.Request("GET", "https://files.example.com/bad.jpg"),
        )
        monkeypatch.setattr(media.httpx, "AsyncClient", FakeAsyncClient)
        bot = FakeBot()
        post = Post("yandere", "1", "https://files.example.com/bad.jpg")

        result = await media.send_post(bot, 123, post, settings=Settings())

        assert result["method"] == "document"
        method, _, document, _ = bot.calls[0]
        assert method == "document"
        assert isinstance(document, BufferedInputFile)
        assert document.data == b"not an image"

    import httpx

    asyncio.run(run())


def test_media_photo_invalid_dimensions_falls_back_to_buffered_document(monkeypatch):
    from aiogram.exceptions import TelegramBadRequest
    from aiogram.methods import SendPhoto
    from aiogram.types import BufferedInputFile

    from app.services import media

    async def run():
        FakeAsyncClient.response = httpx.Response(
            200,
            content=make_image_bytes(image_format="JPEG"),
            headers={"content-type": "image/jpeg"},
            request=httpx.Request("GET", "https://files.example.com/image.jpg"),
        )
        monkeypatch.setattr(media.httpx, "AsyncClient", FakeAsyncClient)
        error = TelegramBadRequest(
            method=SendPhoto(chat_id=123, photo="x"),
            message="Bad Request: PHOTO_INVALID_DIMENSIONS",
        )
        bot = FakeBot(photo_error=error)
        post = Post("yandere", "1265418", "https://files.example.com/image.jpg")

        result = await media.send_post(bot, 123, post, settings=Settings())

        assert result["method"] == "document"
        assert [call[0] for call in bot.calls] == ["photo", "document"]
        _, _, document, _ = bot.calls[1]
        assert isinstance(document, BufferedInputFile)
        assert document.data.startswith(b"\xff\xd8")

    import httpx

    asyncio.run(run())


def test_media_uses_proxy_url_from_settings(monkeypatch):
    from app.services import media

    async def run():
        FakeAsyncClient.response = httpx.Response(
            200,
            content=make_image_bytes(image_format="JPEG"),
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


def callback_data(markup):
    return [button.callback_data for row in markup.inline_keyboard for button in row]


def test_post_nav_keyboard_contains_navigation_callbacks():
    from app.keyboards import post_nav

    assert callback_data(post_nav()) == [
        "post:prev",
        "post:next",
        "post:more",
        "post:fav",
        "menu:home",
    ]


class FakePostProviders:
    def __init__(self):
        self.search_calls = []
        self.random_calls = []

    async def search(self, tags="", provider_name=None, page=1, limit=20, auto=True):
        self.search_calls.append((tags, provider_name, page, limit, auto))
        return provider_name or "gelbooru", [
            Post(provider_name or "gelbooru", "next", "https://example.com/next.jpg", tags=tags)
        ]

    async def random(self, tags="", provider_name=None, auto=True):
        self.random_calls.append((tags, provider_name, auto))
        return Post(provider_name or "gelbooru", "random-next", "https://example.com/random.jpg")


class FakePostContext:
    def __init__(self, db):
        self.db = db
        self.providers = FakePostProviders()


async def seed_current_post(ctx, user_id=7, tags="cat", mode="search"):
    from app.handlers.search import save_shown_post

    await save_shown_post(
        ctx,
        user_id,
        Post("gelbooru", "1", "https://example.com/1.jpg", tags=tags),
        tags=tags,
        mode=mode,
    )


def test_favorite_duplicate_is_ignored(tmp_path):
    from app.handlers.search import add_favorite

    async def run():
        db = Database(str(tmp_path / "bot.sqlite3"))
        await db.migrate()
        ctx = FakePostContext(db)
        await seed_current_post(ctx)

        assert await add_favorite(ctx, 7) is True
        assert await add_favorite(ctx, 7) is False
        rows = await db.fetchall("SELECT * FROM favorites WHERE user_id = ?", (7,))
        assert len(rows) == 1

    asyncio.run(run())


def test_prev_without_history_gives_readable_message(tmp_path):
    from app.handlers.search import post_prev

    class FakeUserForPrev:
        id = 7

    class FakeCallForPrev:
        from_user = FakeUserForPrev()

        def __init__(self):
            self.answer_args = None

        async def answer(self, *args, **kwargs):
            self.answer_args = (args, kwargs)

    async def run():
        db = Database(str(tmp_path / "bot.sqlite3"))
        await db.migrate()
        ctx = FakePostContext(db)
        call = FakeCallForPrev()

        await post_prev(call, ctx)

        assert call.answer_args == (("Это первый пост",), {"show_alert": True})

    asyncio.run(run())


def test_next_more_uses_current_search_context(tmp_path):
    from app.handlers.search import fetch_next_post

    async def run():
        db = Database(str(tmp_path / "bot.sqlite3"))
        await db.migrate()
        ctx = FakePostContext(db)
        await seed_current_post(ctx, tags="cat rating:explicit", mode="search")

        post = await fetch_next_post(ctx, 7)

        assert post.post_id == "next"
        assert ctx.providers.search_calls == [("cat rating:explicit", "gelbooru", 1, 30, False)]

    asyncio.run(run())


def test_home_opens_main_menu():
    from app.handlers.search import post_home

    class FakeMessageForHome:
        def __init__(self):
            self.edited = None

        async def edit_text(self, text, reply_markup=None):
            self.edited = (text, reply_markup)

    class FakeUserForHome:
        id = 7

    class FakeCallForHome:
        data = "menu:home"
        from_user = FakeUserForHome()

        def __init__(self):
            self.message = FakeMessageForHome()
            self.answered = False

        async def answer(self, *args, **kwargs):
            self.answered = True

    call = FakeCallForHome()
    asyncio.run(post_home(call))

    text, markup = call.message.edited
    assert text == "Главное меню"
    assert "random" in callback_data(markup)
    assert call.answered is True


def test_next_does_not_repeat_current_post(tmp_path):
    from app.handlers.search import fetch_next_post

    class DuplicateThenUniqueProviders(FakePostProviders):
        async def search(self, tags="", provider_name=None, page=1, limit=20, auto=True):
            self.search_calls.append((tags, provider_name, page, limit, auto))
            post_id = "1" if len(self.search_calls) == 1 else "2"
            return provider_name or "gelbooru", [
                Post(
                    provider_name or "gelbooru",
                    post_id,
                    f"https://example.com/{post_id}.jpg",
                    tags=tags,
                )
            ]

    async def run():
        db = Database(str(tmp_path / "bot.sqlite3"))
        await db.migrate()
        ctx = FakePostContext(db)
        ctx.providers = DuplicateThenUniqueProviders()
        await seed_current_post(ctx, tags="cat", mode="search")

        post = await fetch_next_post(ctx, 7)

        assert post.post_id == "2"
        rows = await db.fetchall(
            "SELECT post_id FROM post_history WHERE user_id = ? ORDER BY history_index", (7,)
        )
        assert [row["post_id"] for row in rows] == ["1", "2"]

    asyncio.run(run())


def test_more_does_not_repeat_shown_posts(tmp_path):
    from app.handlers.search import fetch_next_post

    class SequenceProviders(FakePostProviders):
        def __init__(self):
            super().__init__()
            self.ids = iter(["1", "2", "2", "3"])

        async def random(self, tags="", provider_name=None, auto=True):
            self.random_calls.append((tags, provider_name, auto))
            post_id = next(self.ids)
            return Post(provider_name or "gelbooru", post_id, f"https://example.com/{post_id}.jpg")

    async def run():
        db = Database(str(tmp_path / "bot.sqlite3"))
        await db.migrate()
        ctx = FakePostContext(db)
        ctx.providers = SequenceProviders()
        await seed_current_post(ctx, tags="", mode="random")

        first = await fetch_next_post(ctx, 7, action="more")
        second = await fetch_next_post(ctx, 7, action="more")

        assert first.post_id == "2"
        assert second.post_id == "3"
        rows = await db.fetchall(
            "SELECT post_id FROM post_history WHERE user_id = ? ORDER BY history_index", (7,)
        )
        assert [row["post_id"] for row in rows] == ["1", "2", "3"]

    asyncio.run(run())


def test_prev_returns_existing_previous_post(tmp_path):
    from app.handlers.search import fetch_next_post, previous_post

    async def run():
        db = Database(str(tmp_path / "bot.sqlite3"))
        await db.migrate()
        ctx = FakePostContext(db)
        await seed_current_post(ctx, tags="cat", mode="search")
        await fetch_next_post(ctx, 7)

        post = await previous_post(ctx, 7)

        assert post.post_id == "1"

    asyncio.run(run())


def test_favorite_does_not_send_new_media(tmp_path):
    from app.handlers.search import post_fav

    class FakeUser:
        id = 7

    class FakeCall:
        from_user = FakeUser()

        def __init__(self):
            self.answer_args = None

        async def answer(self, *args, **kwargs):
            self.answer_args = (args, kwargs)

    async def run():
        db = Database(str(tmp_path / "bot.sqlite3"))
        await db.migrate()
        ctx = FakePostContext(db)
        await seed_current_post(ctx)
        call = FakeCall()

        await post_fav(call, ctx)

        assert call.answer_args == (("Добавлено в избранное",), {})
        assert ctx.providers.random_calls == []
        assert ctx.providers.search_calls == []

    asyncio.run(run())


def test_duplicate_provider_post_id_is_not_appended(tmp_path):
    from app.handlers.search import save_shown_post

    async def run():
        db = Database(str(tmp_path / "bot.sqlite3"))
        await db.migrate()
        ctx = FakePostContext(db)
        post = Post("gelbooru", "1", "https://example.com/1.jpg")

        assert await save_shown_post(ctx, 7, post, tags="cat", mode="search") is True
        assert await save_shown_post(ctx, 7, post, tags="cat", mode="search") is False
        rows = await db.fetchall("SELECT * FROM post_history WHERE user_id = ?", (7,))
        assert len(rows) == 1

    asyncio.run(run())


def test_repeated_duplicate_fetch_returns_readable_callback(tmp_path):
    from app.handlers.search import post_more

    class DuplicateProviders(FakePostProviders):
        async def random(self, tags="", provider_name=None, auto=True):
            self.random_calls.append((tags, provider_name, auto))
            return Post(provider_name or "gelbooru", "1", "https://example.com/1.jpg")

    class FakeUser:
        id = 7

    class FakeCall:
        from_user = FakeUser()

        def __init__(self):
            self.answer_args = None

        async def answer(self, *args, **kwargs):
            self.answer_args = (args, kwargs)

    async def run():
        db = Database(str(tmp_path / "bot.sqlite3"))
        await db.migrate()
        ctx = FakePostContext(db)
        ctx.providers = DuplicateProviders()
        await seed_current_post(ctx, tags="", mode="random")
        call = FakeCall()

        await post_more(call, ctx)

        assert call.answer_args == (("Не нашла новый арт, попробуй ещё раз",), {"show_alert": True})
        rows = await db.fetchall("SELECT * FROM post_history WHERE user_id = ?", (7,))
        assert len(rows) == 1

    asyncio.run(run())
