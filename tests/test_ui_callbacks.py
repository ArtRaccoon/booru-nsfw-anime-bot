import asyncio
from datetime import UTC, datetime, timedelta

from app.keyboards import history_keyboard, main_menu_keyboard, post_keyboard, providers_keyboard
from app.models import BooruPost
from app.providers.registry import fallback_search
from app.ui.sessions import CallbackSessions, SearchSession, callback_data, parse_callback
from app.ui.texts import ALL_PROVIDERS_FAILED


def test_callback_data_with_rating_explicit_does_not_crash():
    assert parse_callback("next:abc123") == ("next", "abc123")
    assert "rating:explicit" not in callback_data("next", "abc123")


def test_multiple_colon_tags_do_not_crash_parser():
    assert parse_callback("repeat:key:with:colons") == ("repeat", "key:with:colons")


def test_callback_data_length_under_64():
    data = callback_data("repeat", "abc123")
    assert len(data.encode()) <= 64
    markup = post_keyboard("abc123", 1)
    for row in markup.inline_keyboard:
        for button in row:
            if button.callback_data:
                assert len(button.callback_data.encode()) <= 64


def test_expired_session_handled():
    sessions = CallbackSessions(ttl=timedelta(minutes=30))
    key = sessions.create(SearchSession(user_id=1, provider="danbooru", query="rating:explicit"))
    sessions._sessions[key].created_at = datetime.now(UTC) - timedelta(minutes=31)
    assert sessions.get(key, 1) is None


def test_provider_pagination_keyboard():
    markup = providers_keyboard([f"p{i}" for i in range(10)], selected="p0", page=0)
    texts = [button.text for row in markup.inline_keyboard for button in row]
    callbacks = [button.callback_data for row in markup.inline_keyboard for button in row]
    assert "✅ p0" in texts
    assert "➡️" in texts
    assert "providers_page:1" in callbacks
    assert "🏠 Меню" in texts


def test_main_menu_keyboard():
    markup = main_menu_keyboard(is_admin=True)
    texts = [button.text for row in markup.inline_keyboard for button in row]
    assert "🎲 Случайный арт" in texts
    assert "🔎 Поиск" in texts
    assert "🛠 Админка" in texts


def test_history_repeat_callback():
    markup = history_keyboard(["rating:explicit", "1girl long_hair"])
    callbacks = [button.callback_data for row in markup.inline_keyboard for button in row]
    assert "history_repeat:0" in callbacks
    assert "history_repeat:1" in callbacks


def test_favorite_callback():
    data = callback_data("fav", "abc123")
    assert data == "fav:abc123"
    assert parse_callback(data) == ("fav", "abc123")


def test_all_providers_fail_returns_user_friendly_message():
    provider, posts = asyncio.run(fallback_search({}, "rating:explicit", 1, 1))
    assert provider is None
    assert posts == []
    assert ALL_PROVIDERS_FAILED == "Все активные источники временно недоступны."


def test_session_stores_search_payload():
    post = BooruPost(provider="danbooru", post_id="1", file_url="https://example.com/1.jpg")
    session = SearchSession(
        user_id=7,
        provider="danbooru",
        query="rating:explicit tag:with:colons",
        page=2,
        current_post_id="1",
        results=[post],
    )
    sessions = CallbackSessions()
    key = sessions.create(session)
    restored = sessions.get(key, 7)
    assert restored is not None
    assert restored.query == "rating:explicit tag:with:colons"
    assert restored.current_post_id == "1"
