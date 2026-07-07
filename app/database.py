from datetime import UTC, datetime
from pathlib import Path

import aiosqlite


class Database:
    def __init__(self, path: str) -> None:
        self.path = path
        self.conn: aiosqlite.Connection | None = None

    async def connect(self) -> None:
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = await aiosqlite.connect(self.path)
        self.conn.row_factory = aiosqlite.Row
        await self.migrate()

    async def migrate(self) -> None:
        assert self.conn
        await self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
              telegram_id INTEGER PRIMARY KEY,
              username TEXT,
              is_adult_confirmed INTEGER NOT NULL DEFAULT 0,
              selected_provider TEXT,
              created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS favorites (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              telegram_id INTEGER NOT NULL,
              provider TEXT NOT NULL,
              post_id TEXT NOT NULL,
              file_url TEXT NOT NULL,
              tags TEXT NOT NULL,
              created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS search_history (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              telegram_id INTEGER NOT NULL,
              provider TEXT NOT NULL,
              query TEXT NOT NULL,
              created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS tag_usage (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              telegram_id INTEGER NOT NULL,
              username TEXT,
              provider TEXT,
              query TEXT,
              tag TEXT NOT NULL,
              created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS group_posting_settings (
              id INTEGER PRIMARY KEY,
              target_chat_id INTEGER,
              enabled INTEGER DEFAULT 0,
              mode TEXT DEFAULT 'sfw',
              provider TEXT,
              tags TEXT,
              interval_minutes INTEGER DEFAULT 180,
              last_posted_at TEXT,
              created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
              updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS group_post_history (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              target_chat_id INTEGER,
              provider TEXT,
              post_id TEXT,
              file_url TEXT,
              tags TEXT,
              posted_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE UNIQUE INDEX IF NOT EXISTS idx_group_post_unique
              ON group_post_history(target_chat_id, provider, post_id);
            INSERT OR IGNORE INTO group_posting_settings(id) VALUES(1);
            """
        )
        await self.conn.commit()

    async def upsert_user(self, telegram_id: int, username: str | None) -> None:
        assert self.conn
        await self.conn.execute(
            "INSERT INTO users(telegram_id, username) VALUES(?, ?) "
            "ON CONFLICT(telegram_id) DO UPDATE SET username=excluded.username",
            (telegram_id, username),
        )
        await self.conn.commit()

    async def confirm_adult(self, telegram_id: int) -> None:
        assert self.conn
        await self.conn.execute(
            "UPDATE users SET is_adult_confirmed=1 WHERE telegram_id=?", (telegram_id,)
        )
        await self.conn.commit()

    async def is_confirmed(self, telegram_id: int) -> bool:
        assert self.conn
        row = await (
            await self.conn.execute(
                "SELECT is_adult_confirmed FROM users WHERE telegram_id=?", (telegram_id,)
            )
        ).fetchone()
        return bool(row and row["is_adult_confirmed"])

    async def set_provider(self, telegram_id: int, provider: str) -> None:
        assert self.conn
        await self.conn.execute(
            "UPDATE users SET selected_provider=? WHERE telegram_id=?", (provider, telegram_id)
        )
        await self.conn.commit()

    async def get_provider(self, telegram_id: int, default: str) -> str:
        assert self.conn
        row = await (
            await self.conn.execute(
                "SELECT selected_provider FROM users WHERE telegram_id=?", (telegram_id,)
            )
        ).fetchone()
        return row["selected_provider"] if row and row["selected_provider"] else default

    async def add_favorite(
        self, telegram_id: int, provider: str, post_id: str, file_url: str, tags: list[str]
    ) -> None:
        assert self.conn
        await self.conn.execute(
            "INSERT INTO favorites(telegram_id, provider, post_id, file_url, tags) "
            "VALUES(?, ?, ?, ?, ?)",
            (telegram_id, provider, post_id, file_url, " ".join(tags)),
        )
        await self.conn.commit()

    async def add_history(self, telegram_id: int, provider: str, query: str) -> None:
        assert self.conn
        await self.conn.execute(
            "INSERT INTO search_history(telegram_id, provider, query) VALUES(?, ?, ?)",
            (telegram_id, provider, query),
        )
        await self.conn.commit()

    async def list_favorites(self, telegram_id: int, limit: int = 20, offset: int = 0):
        assert self.conn
        return await (
            await self.conn.execute(
                "SELECT * FROM favorites WHERE telegram_id=? ORDER BY id DESC LIMIT ? OFFSET ?",
                (telegram_id, limit, offset),
            )
        ).fetchall()

    async def count_favorites(self, telegram_id: int) -> int:
        assert self.conn
        row = await (
            await self.conn.execute(
                "SELECT COUNT(*) c FROM favorites WHERE telegram_id=?", (telegram_id,)
            )
        ).fetchone()
        return int(row["c"])

    async def remove_favorite(self, telegram_id: int, favorite_id: int) -> None:
        assert self.conn
        await self.conn.execute(
            "DELETE FROM favorites WHERE telegram_id=? AND id=?", (telegram_id, favorite_id)
        )
        await self.conn.commit()

    async def recent_history(self, telegram_id: int, limit: int = 10):
        assert self.conn
        return await (
            await self.conn.execute(
                "SELECT query, MAX(created_at) created_at FROM search_history "
                "WHERE telegram_id=? GROUP BY query ORDER BY created_at DESC LIMIT ?",
                (telegram_id, limit),
            )
        ).fetchall()

    async def clear_history(self, telegram_id: int) -> None:
        assert self.conn
        await self.conn.execute("DELETE FROM search_history WHERE telegram_id=?", (telegram_id,))
        await self.conn.commit()

    async def get_stats(self) -> dict[str, int]:
        assert self.conn
        users = (await (await self.conn.execute("SELECT COUNT(*) c FROM users")).fetchone())["c"]
        favorites = (
            await (await self.conn.execute("SELECT COUNT(*) c FROM favorites")).fetchone()
        )["c"]
        searches = (
            await (await self.conn.execute("SELECT COUNT(*) c FROM search_history")).fetchone()
        )["c"]
        return {"users": users, "favorites": favorites, "searches": searches}

    async def add_tag_usage(
        self,
        telegram_id: int,
        username: str | None,
        provider: str | None,
        query: str,
        tags: list[str],
    ) -> None:
        assert self.conn
        await self.conn.executemany(
            """
            INSERT INTO tag_usage(telegram_id, username, provider, query, tag)
            VALUES(?, ?, ?, ?, ?)
            """,
            [(telegram_id, username, provider, query, tag) for tag in tags if tag],
        )
        await self.conn.commit()

    async def top_tags(self, limit: int = 30, telegram_id: int | None = None):
        assert self.conn
        if telegram_id is None:
            return await (
                await self.conn.execute(
                    """
                    SELECT tag, COUNT(*) count FROM tag_usage
                    GROUP BY tag ORDER BY count DESC, tag LIMIT ?
                    """,
                    (limit,),
                )
            ).fetchall()
        return await (
            await self.conn.execute(
                """
                SELECT tag, COUNT(*) count FROM tag_usage WHERE telegram_id=?
                GROUP BY tag ORDER BY count DESC, tag LIMIT ?
                """,
                (telegram_id, limit),
            )
        ).fetchall()

    async def users_by_tag(self, tag: str, limit: int = 30):
        assert self.conn
        return await (
            await self.conn.execute(
                """
                SELECT telegram_id, username, COUNT(*) count FROM tag_usage WHERE tag=?
                GROUP BY telegram_id, username ORDER BY count DESC LIMIT ?
                """,
                (tag, limit),
            )
        ).fetchall()

    async def user_searches(self, telegram_id: int, limit: int = 20):
        assert self.conn
        return await (
            await self.conn.execute(
                """
                SELECT query, provider, MAX(created_at) created_at FROM tag_usage
                WHERE telegram_id=? GROUP BY query, provider ORDER BY created_at DESC LIMIT ?
                """,
                (telegram_id, limit),
            )
        ).fetchall()

    async def get_group_posting_settings(self):
        assert self.conn
        return await (
            await self.conn.execute("SELECT * FROM group_posting_settings WHERE id=1")
        ).fetchone()

    async def update_group_posting_settings(self, **fields) -> None:
        assert self.conn
        if "interval_minutes" in fields:
            fields["interval_minutes"] = max(15, int(fields["interval_minutes"]))
        fields["updated_at"] = datetime.now(UTC).replace(microsecond=0).isoformat()
        assignments = ", ".join(f"{key}=?" for key in fields)
        await self.conn.execute(
            f"UPDATE group_posting_settings SET {assignments} WHERE id=1",
            tuple(fields.values()),
        )
        await self.conn.commit()

    async def group_post_seen(self, target_chat_id: int | str, provider: str, post_id: str) -> bool:
        assert self.conn
        row = await (
            await self.conn.execute(
                """
                SELECT 1 FROM group_post_history
                WHERE target_chat_id=? AND provider=? AND post_id=?
                """,
                (target_chat_id, provider, post_id),
            )
        ).fetchone()
        return row is not None

    async def add_group_post_history(
        self, target_chat_id: int | str, provider: str, post_id: str, file_url: str, tags: str
    ) -> None:
        assert self.conn
        await self.conn.execute(
            """
            INSERT OR IGNORE INTO group_post_history(
                target_chat_id, provider, post_id, file_url, tags
            ) VALUES(?, ?, ?, ?, ?)
            """,
            (target_chat_id, provider, post_id, file_url, tags),
        )
        await self.conn.commit()

    async def group_history(self, limit: int = 10):
        assert self.conn
        return await (
            await self.conn.execute(
                "SELECT * FROM group_post_history ORDER BY id DESC LIMIT ?", (limit,)
            )
        ).fetchall()

    async def group_history_stats(self, target_chat_id: int | str | None = None, limit: int = 10):
        assert self.conn
        where = "WHERE target_chat_id=?" if target_chat_id else ""
        params = (target_chat_id, limit) if target_chat_id else (limit,)
        total = await (
            await self.conn.execute(
                f"SELECT COUNT(*) c FROM group_post_history {where}",
                (target_chat_id,) if target_chat_id else (),
            )
        ).fetchone()
        rows = await (
            await self.conn.execute(
                f"SELECT * FROM group_post_history {where} ORDER BY id DESC LIMIT ?", params
            )
        ).fetchall()
        last = rows[0]["posted_at"] if rows else None
        return {"total": int(total["c"]), "rows": rows, "last": last}

    async def clear_group_history(self, target_chat_id: int | str) -> None:
        assert self.conn
        await self.conn.execute(
            "DELETE FROM group_post_history WHERE target_chat_id=?", (target_chat_id,)
        )
        await self.conn.commit()

    async def touch_group_posted_at(self, value: str) -> None:
        await self.update_group_posting_settings(last_posted_at=value)
