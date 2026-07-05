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
