import asyncio

from app.database import Database
from app.group_posting import find_unique_post, split_tag_blocks, tags_for_mode
from app.keyboards import admin_keyboard, main_menu_keyboard
from app.models import BooruPost


class Provider:
    name = "danbooru"

    def __init__(self, posts):
        self.posts = posts
        self.calls = 0

    async def search(self, tags, limit, page):
        post = self.posts[min(self.calls, len(self.posts) - 1)]
        self.calls += 1
        return [post]


def button_texts(markup):
    return [button.text for row in markup.inline_keyboard for button in row]


def test_regular_menu_does_not_show_admin_controls():
    assert "🛠 Админка" not in button_texts(main_menu_keyboard(is_admin=False))
    texts = button_texts(admin_keyboard())
    assert "📊 Статистика" in texts
    assert "🏷 Статистика тегов" in texts
    assert "🛰 Групповой постинг" in texts


def test_tag_usage_stats_and_group_settings(tmp_path):
    async def run():
        db = Database(str(tmp_path / "bot.sqlite3"))
        await db.connect()
        try:
            await db.add_tag_usage(1, "alice", "danbooru", "cat girl", ["cat", "girl"])
            await db.add_tag_usage(2, "bob", "danbooru", "cat", ["cat"])
            assert [(r["tag"], r["count"]) for r in await db.top_tags()] == [
                ("cat", 2),
                ("girl", 1),
            ]
            assert [(r["tag"], r["count"]) for r in await db.top_tags(30, 1)] == [
                ("cat", 1),
                ("girl", 1),
            ]
            users = await db.users_by_tag("cat")
            assert [(r["telegram_id"], r["username"], r["count"]) for r in users] == [
                (1, "alice", 1),
                (2, "bob", 1),
            ]
            searches = await db.user_searches(1)
            assert searches[0]["query"] == "cat girl"

            await db.update_group_posting_settings(target_chat_id=-100, enabled=1)
            await db.update_group_posting_settings(mode="nsfw", tags="solo", interval_minutes=5)
            row = await db.get_group_posting_settings()
            assert row["target_chat_id"] == -100
            assert row["enabled"] == 1
            assert row["mode"] == "nsfw"
            assert row["tags"] == "solo"
            assert row["interval_minutes"] == 15
        finally:
            await db.conn.close()

    asyncio.run(run())


def test_no_repeat_retries_and_skips(tmp_path):
    async def run():
        db = Database(str(tmp_path / "bot.sqlite3"))
        await db.connect()
        try:
            await db.update_group_posting_settings(target_chat_id=-100)
            duplicate = BooruPost(provider="danbooru", post_id="1", file_url="u", tags=["a"])
            unique = BooruPost(provider="danbooru", post_id="2", file_url="u2", tags=["b"])
            await db.add_group_post_history(-100, "danbooru", "1", "u", "a")
            provider = Provider([duplicate, unique])
            found = await find_unique_post(
                db, {"danbooru": provider}, dict(await db.get_group_posting_settings())
            )
            assert found.post_id == "2"
            assert provider.calls == 2

            only_duplicate = Provider([duplicate])
            found = await find_unique_post(
                db, {"danbooru": only_duplicate}, dict(await db.get_group_posting_settings())
            )
            assert found is None
            assert only_duplicate.calls == 10
        finally:
            await db.conn.close()

    asyncio.run(run())


def test_formatting_escapes_html_and_splits():
    assert tags_for_mode("sfw", "cat") == "cat rating:safe"
    assert tags_for_mode("nsfw", "cat") == "cat rating:explicit"
    assert tags_for_mode("mixed", "cat") == "cat"
    blocks = split_tag_blocks(["<bad&tag>", "x" * 40], max_len=70)
    assert "&lt;bad&amp;tag&gt;" in blocks[0]
    assert len(blocks) > 1
