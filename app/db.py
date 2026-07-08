from __future__ import annotations

from pathlib import Path
from typing import Any

import aiosqlite

SCHEMA = [
    """CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        selected_provider TEXT,
        auto_mode INTEGER NOT NULL DEFAULT 1,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )""",
    """CREATE TABLE IF NOT EXISTS favorites (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        provider TEXT NOT NULL,
        post_id TEXT NOT NULL,
        file_url TEXT NOT NULL,
        page_url TEXT,
        rating TEXT,
        tags TEXT,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(user_id, provider, post_id)
    )""",
    """CREATE TABLE IF NOT EXISTS search_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        provider TEXT NOT NULL,
        tags TEXT NOT NULL,
        post_id TEXT,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )""",
    """CREATE TABLE IF NOT EXISTS provider_settings (
        provider TEXT PRIMARY KEY,
        enabled INTEGER NOT NULL DEFAULT 1,
        updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )""",
    """CREATE TABLE IF NOT EXISTS channel_settings (
        id INTEGER PRIMARY KEY CHECK (id = 1),
        channel_id TEXT,
        enabled INTEGER NOT NULL DEFAULT 0,
        mode TEXT NOT NULL DEFAULT 'mixed',
        tags TEXT NOT NULL DEFAULT '',
        interval_minutes INTEGER NOT NULL DEFAULT 60,
        source_mode TEXT NOT NULL DEFAULT 'auto',
        selected_provider TEXT
    )""",
    """CREATE TABLE IF NOT EXISTS channel_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        provider TEXT NOT NULL,
        post_id TEXT NOT NULL,
        posted_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(provider, post_id)
    )""",
    """CREATE TABLE IF NOT EXISTS tag_usage (
        tag TEXT PRIMARY KEY,
        uses INTEGER NOT NULL DEFAULT 0,
        updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )""",
]


class Database:
    def __init__(self, path: str):
        self.path = path

    async def connect(self) -> aiosqlite.Connection:
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        db = await aiosqlite.connect(self.path)
        db.row_factory = aiosqlite.Row
        return db

    async def migrate(self) -> None:
        db = await self.connect()
        try:
            for stmt in SCHEMA:
                await db.execute(stmt)
            await db.execute("INSERT OR IGNORE INTO channel_settings (id) VALUES (1)")
            await db.commit()
        finally:
            await db.close()

    async def execute(self, sql: str, params: tuple[Any, ...] = ()) -> None:
        db = await self.connect()
        try:
            await db.execute(sql, params)
            await db.commit()
        finally:
            await db.close()

    async def fetchall(self, sql: str, params: tuple[Any, ...] = ()) -> list[aiosqlite.Row]:
        db = await self.connect()
        try:
            cur = await db.execute(sql, params)
            return await cur.fetchall()
        finally:
            await db.close()

    async def fetchone(self, sql: str, params: tuple[Any, ...] = ()) -> aiosqlite.Row | None:
        db = await self.connect()
        try:
            cur = await db.execute(sql, params)
            return await cur.fetchone()
        finally:
            await db.close()
