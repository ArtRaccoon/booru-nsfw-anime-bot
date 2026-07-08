import asyncio
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

from app.handlers import favorites, search
from app.models import BooruPost
from app.ui.sessions import SearchSession, callback_sessions
from app.ui.texts import SESSION_EXPIRED


class DummyTarget:
    def __init__(self, user_id: int = 1):
        self.from_user = SimpleNamespace(id=user_id, username="u")
        self.chat = SimpleNamespace(id=10)
        self.bot = SimpleNamespace(
            edit_message_text=AsyncMock(),
            delete_message=AsyncMock(),
            edit_message_media=AsyncMock(),
            edit_message_caption=AsyncMock(),
        )
        self.answer = AsyncMock(side_effect=self._answer)
        self.answer_photo = AsyncMock(side_effect=self._answer_photo)
        self.answer_document = AsyncMock(side_effect=self._answer_photo)
        self._next_id = 100

    def _message(self):
        self._next_id += 1
        return SimpleNamespace(message_id=self._next_id)

    async def _answer(self, *args, **kwargs):
        return self._message()

    async def _answer_photo(self, *args, **kwargs):
        return self._message()


def setup_function():
    callback_sessions._sessions.clear()


def test_search_session_stores_message_ids():
    session = SearchSession(
        user_id=1,
        provider="danbooru",
        query="rating:explicit",
        image_message_id=11,
        tags_message_ids=[12, 13],
        current_post_id="p1",
        current_page=2,
        current_provider="danbooru",
    )

    key = callback_sessions.create(session)
    restored = callback_sessions.get(key, 1)

    assert restored is not None
    assert restored.image_message_id == 11
    assert restored.tags_message_ids == [12, 13]
    assert restored.current_page == 2
    assert restored.current_provider == "danbooru"


def test_update_tags_same_number_edits_existing_messages():
    target = DummyTarget()
    session = SearchSession(user_id=1, provider="p", query="q", tags_message_ids=[1, 2])

    asyncio.run(search._update_tags_messages(target, session, ["a", "b"]))

    assert session.tags_message_ids == [1, 2]
    assert target.bot.edit_message_text.await_count == 2
    target.answer.assert_not_awaited()
    target.bot.delete_message.assert_not_awaited()


def test_update_tags_more_messages_sends_additional_messages():
    target = DummyTarget()
    session = SearchSession(user_id=1, provider="p", query="q", tags_message_ids=[1])

    asyncio.run(search._update_tags_messages(target, session, ["a", "b"]))

    assert session.tags_message_ids == [1, 101]
    assert target.bot.edit_message_text.await_count == 1
    assert target.answer.await_count == 1


def test_update_tags_fewer_messages_deletes_extra_messages():
    target = DummyTarget()
    session = SearchSession(user_id=1, provider="p", query="q", tags_message_ids=[1, 2])

    asyncio.run(search._update_tags_messages(target, session, ["a"]))

    assert session.tags_message_ids == [1]
    target.bot.delete_message.assert_awaited_once_with(chat_id=10, message_id=2)


def test_expired_session_callback_answers_friendly_message():
    target = DummyTarget()
    callback = SimpleNamespace(
        data="next:expired",
        from_user=SimpleNamespace(id=1, username="u"),
        message=target,
        answer=AsyncMock(),
    )
    callback_sessions._sessions["expired"] = SearchSession(user_id=1, provider="p", query="q")
    callback_sessions._sessions["expired"].created_at = datetime.now(UTC) - timedelta(minutes=31)

    asyncio.run(search.page_or_repeat(callback, db=object(), settings=object(), providers_map={}))

    callback.answer.assert_awaited_once_with(SESSION_EXPIRED, show_alert=True)


def test_favorite_callback_answers_without_sending_message():
    post = BooruPost(provider="danbooru", post_id="1", file_url="https://example.com/1.jpg")
    session = SearchSession(user_id=1, provider="danbooru", query="q", current_post_id="1")
    key = callback_sessions.create(session)
    search.post_cache[(1, "1")] = post
    callback = SimpleNamespace(
        data=f"fav:{key}",
        from_user=SimpleNamespace(id=1),
        message=DummyTarget(),
        answer=AsyncMock(),
    )
    db = SimpleNamespace(add_favorite=AsyncMock())

    asyncio.run(favorites.save_favorite(callback, db))

    callback.answer.assert_awaited_once_with("Добавлено в избранное.")
    callback.message.answer.assert_not_awaited()
    callback.message.answer_photo.assert_not_awaited()


def test_non_photo_posts_are_sent_as_documents(monkeypatch):
    target = DummyTarget()
    session = SearchSession(user_id=1, provider="danbooru", query="q")
    key = callback_sessions.create(session)
    post = BooruPost(
        provider="danbooru",
        post_id="3",
        file_url="https://cdn.test/3.webm?download=1",
        tags=["animated"],
    )

    async def fake_fetch(*args, **kwargs):
        assert kwargs["proxy_url"] == "socks5://127.0.0.1:1080"
        return b"video"

    monkeypatch.setattr(search, "fetch_image_bytes", fake_fetch)

    asyncio.run(
        search.render_post(target, key, post, 1, user_id=1, proxy_url="socks5://127.0.0.1:1080")
    )

    target.answer_document.assert_awaited_once()
    target.answer_photo.assert_not_awaited()
    sent_file = target.answer_document.await_args.args[0]
    assert sent_file.filename == "danbooru_3.webm"


def test_render_update_errors_are_logged_not_raised(caplog):
    target = DummyTarget()
    target.bot.edit_message_media.side_effect = RuntimeError("edit failed")
    target.bot.delete_message.side_effect = RuntimeError("delete failed")
    target.answer_photo.side_effect = RuntimeError("photo failed")
    target.bot.edit_message_text.side_effect = RuntimeError("text failed")
    target.answer.side_effect = RuntimeError("fallback failed")
    session = SearchSession(
        user_id=1,
        provider="danbooru",
        query="q",
        image_message_id=50,
        tags_message_ids=[51],
    )
    key = callback_sessions.create(session)
    post = BooruPost(
        provider="danbooru",
        post_id="2",
        file_url="https://example.com/2.jpg",
        tags=["tag"],
    )

    asyncio.run(search.render_post(target, key, post, 1, update_existing=True, user_id=1))

    assert "failed to edit post media" in caplog.text
    assert "failed to send replacement fallback" in caplog.text
