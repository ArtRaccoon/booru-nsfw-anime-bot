from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from urllib.parse import urlsplit, urlunsplit

from aiogram import Bot, Dispatcher
from aiogram.client.session.aiohttp import AiohttpSession

from app.config import get_settings
from app.db import Database
from app.services.channel_posting import ChannelPostingService
from app.services.providers import ProviderManager


@dataclass
class AppContext:
    db: Database
    providers: ProviderManager
    channel: ChannelPostingService


_context: AppContext | None = None


def get_context() -> AppContext:
    if _context is None:
        raise RuntimeError("Application context is not initialized")
    return _context


async def create_context() -> AppContext:
    settings = get_settings()
    db = Database(settings.database_path)
    await db.migrate()
    providers = ProviderManager(settings, db)
    await providers.ensure_settings()
    return AppContext(db=db, providers=providers, channel=ChannelPostingService(db, providers))


def _aiogram_proxy_url(proxy_url: str) -> str:
    parsed = urlsplit(proxy_url)
    if parsed.scheme == "socks5h":
        return urlunsplit(parsed._replace(scheme="socks5"))
    return proxy_url


def create_bot(settings) -> Bot:
    if settings.proxy_url:
        logging.info("Telegram proxy enabled: %s", settings.proxy_url)
        session = AiohttpSession(proxy=_aiogram_proxy_url(settings.proxy_url))
        return Bot(token=settings.bot_token, session=session)
    logging.info("Telegram proxy disabled")
    return Bot(token=settings.bot_token)


def build_dispatcher() -> Dispatcher:
    from app.handlers import admin, channel, favorites, search, sources, start

    dp = Dispatcher()
    for router in (
        start.router,
        search.router,
        favorites.router,
        sources.router,
        admin.router,
        channel.router,
    ):
        dp.include_router(router)
    return dp


async def main() -> None:
    global _context
    logging.basicConfig(level=logging.INFO)
    settings = get_settings()
    if not settings.bot_token:
        raise RuntimeError("BOT_TOKEN is required to start Telegram polling")
    _context = await create_context()
    bot = create_bot(settings)
    await build_dispatcher().start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
