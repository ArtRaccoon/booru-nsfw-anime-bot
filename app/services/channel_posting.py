from __future__ import annotations

from aiogram import Bot

from app.db import Database
from app.services.media import send_post
from app.services.providers import ProviderManager


class ChannelPostingService:
    def __init__(self, db: Database, providers: ProviderManager):
        self.db = db
        self.providers = providers

    async def settings(self):
        return await self.db.fetchone("SELECT * FROM channel_settings WHERE id = 1")

    async def update(self, **values: object) -> None:
        allowed = {
            "channel_id",
            "enabled",
            "mode",
            "tags",
            "interval_minutes",
            "source_mode",
            "selected_provider",
        }
        parts = [f"{k} = ?" for k in values if k in allowed]
        if parts:
            await self.db.execute(
                f"UPDATE channel_settings SET {', '.join(parts)} WHERE id = 1",
                tuple(values[k] for k in values if k in allowed),
            )

    async def post_now(self, bot: Bot) -> str:
        s = await self.settings()
        if not s or not s["channel_id"]:
            return "Канал не привязан."
        auto = s["source_mode"] != "selected"
        post = await self.providers.random(s["tags"] or "", s["selected_provider"], auto)
        if not post:
            return "Не удалось найти пост."
        exists = await self.db.fetchone(
            "SELECT 1 FROM channel_history WHERE provider = ? AND post_id = ?",
            (post.provider, post.post_id),
        )
        if exists:
            return "Пост уже был отправлен, попробуйте еще раз."
        await send_post(bot, s["channel_id"], post)
        await self.db.execute(
            "INSERT OR IGNORE INTO channel_history(provider, post_id) VALUES (?, ?)",
            (post.provider, post.post_id),
        )
        return f"Отправлено: {post.provider} #{post.post_id}"
