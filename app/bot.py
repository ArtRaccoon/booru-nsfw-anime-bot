import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.session.aiohttp import AiohttpSession

from app.config import get_settings
from app.database import Database
from app.handlers import admin, favorites, providers, search, start
from app.providers import build_providers


def create_bot(bot_token: str, proxy_url: str | None = None) -> Bot:
    if proxy_url:
        session = AiohttpSession(proxy=proxy_url)
        return Bot(bot_token, session=session)
    return Bot(bot_token)


async def main() -> None:
    logging.basicConfig(level=logging.INFO)
    settings = get_settings()
    if not settings.bot_token:
        raise RuntimeError("BOT_TOKEN is required")
    db = Database(settings.database_path)
    await db.connect()
    providers_map = build_providers(settings)
    if settings.default_provider not in providers_map:
        raise RuntimeError(f"DEFAULT_PROVIDER {settings.default_provider!r} is not configured")

    bot = create_bot(settings.bot_token, settings.proxy_url)
    dp = Dispatcher(db=db, settings=settings, providers_map=providers_map)
    for router in (start.router, providers.router, search.router, favorites.router, admin.router):
        dp.include_router(router)
    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()
        for provider in providers_map.values():
            await provider.close()


if __name__ == "__main__":
    asyncio.run(main())
