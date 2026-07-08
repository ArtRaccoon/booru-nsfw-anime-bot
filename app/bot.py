from __future__ import annotations

import asyncio
import logging
from urllib.parse import urlsplit, urlunsplit

from aiogram import Bot, Dispatcher
from aiogram.client.session.aiohttp import AiohttpSession

from app.config import Settings, get_settings
from app.handlers.start import router as start_router


def _aiogram_proxy_url(proxy_url: str) -> str:
    parsed = urlsplit(proxy_url)
    if parsed.scheme == "socks5h":
        return urlunsplit(parsed._replace(scheme="socks5"))
    return proxy_url


def create_bot(settings: Settings) -> Bot:
    if settings.proxy_url:
        logging.info("Telegram proxy enabled")
        session = AiohttpSession(proxy=_aiogram_proxy_url(settings.proxy_url))
        return Bot(token=settings.bot_token, session=session)

    logging.info("Telegram proxy disabled")
    return Bot(token=settings.bot_token)


def build_dispatcher() -> Dispatcher:
    dp = Dispatcher()
    dp.include_router(start_router)
    return dp


async def main() -> None:
    logging.basicConfig(level=logging.INFO)
    logging.info("Bot starting")

    settings = get_settings()
    if not settings.bot_token:
        raise RuntimeError("BOT_TOKEN is required to start Telegram polling")

    bot = create_bot(settings)
    try:
        await build_dispatcher().start_polling(bot)
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
