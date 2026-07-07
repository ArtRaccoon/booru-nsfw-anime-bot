import asyncio

from app.channel_posting import (
    POSITIVE_ID_WARNING,
    format_caption,
    positive_id_warning,
    resolve_channel_target,
    split_tag_blocks,
)
from app.database import Database
from app.handlers.group_posting import channel_status_text
from app.keyboards import channel_mode_keyboard, channel_posting_keyboard, channel_provider_keyboard
from app.models import BooruPost


def button_texts(markup):
    return [button.text for row in markup.inline_keyboard for button in row]


def test_channel_bind_numeric_minus_100_id():
    assert resolve_channel_target("-1001234567890") == -1001234567890


def test_channel_bind_username():
    assert resolve_channel_target("@channel_name") == "@channel_name"


def test_positive_id_warning():
    assert positive_id_warning(12345) == POSITIVE_ID_WARNING
    assert positive_id_warning(-100123) is None


def test_channel_status_text_renders(tmp_path):
    async def run():
        db = Database(str(tmp_path / "bot.sqlite3"))
        await db.connect()
        try:
            await db.update_group_posting_settings(target_chat_id=-100123, enabled=1)
            text = await channel_status_text(db)
            assert "📢 Постинг в канал" in text
            assert "Статус: включён" in text
            assert "Канал: -100123" in text
            assert "История: 0 постов" in text
        finally:
            await db.conn.close()

    asyncio.run(run())


def test_inline_keyboard_contains_management_buttons():
    texts = button_texts(channel_posting_keyboard())
    for expected in [
        "▶️ Включить",
        "⏸ Выключить",
        "🚀 Пост сейчас",
        "🧪 Тест канала",
        "🎚 Режим",
        "🏷 Теги",
        "🌐 Источник",
        "⏱ Интервал",
        "📜 История",
        "🧹 Сброс истории",
        "🔗 Привязать",
        "🏠 Меню",
    ]:
        assert expected in texts


def test_mode_buttons_and_provider_auto_selection():
    assert {"SFW", "NSFW", "MIXED"}.issubset(set(button_texts(channel_mode_keyboard())))
    assert "auto" in button_texts(channel_provider_keyboard(["danbooru"]))


def test_interval_min_15_and_no_repeat_history_uses_channel_target(tmp_path):
    async def run():
        db = Database(str(tmp_path / "bot.sqlite3"))
        await db.connect()
        try:
            await db.update_group_posting_settings(interval_minutes=1)
            assert (await db.get_group_posting_settings())["interval_minutes"] == 15
            await db.add_group_post_history(-1001, "danbooru", "42", "url", "tags")
            assert await db.group_post_seen(-1001, "danbooru", "42")
            assert not await db.group_post_seen(-1002, "danbooru", "42")
        finally:
            await db.conn.close()

    asyncio.run(run())


def test_html_tags_are_escaped_and_expandable_fallback_shape():
    post = BooruPost(
        provider="danbooru",
        post_id="<42>",
        file_url="http://example.test/a.jpg",
        tags=["a<b", "c&d"],
        rating="safe",
    )
    assert "&lt;42&gt;" in format_caption(post)
    expandable = split_tag_blocks(post.tags, expandable=True)[0]
    fallback = split_tag_blocks(post.tags, expandable=False)[0]
    assert "a&lt;b" in expandable
    assert "c&amp;d" in expandable
    assert "<blockquote expandable>" in expandable
    assert "<blockquote>" in fallback
