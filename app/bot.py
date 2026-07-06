import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.session.aiohttp import AiohttpSession

from app.config import get_settings
from app.database import Database
from app.handlers import admin, favorites, menu, providers, search, start
from app.providers import build_registry


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
    provider_registry = build_registry(settings)
    providers_map = provider_registry.providers
    selected_default = provider_registry.select_default(settings.default_provider)
    if selected_default != settings.default_provider:
        logging.getLogger("providers").warning(
            "Configured DEFAULT_PROVIDER %r is unavailable; using %r",
            settings.default_provider,
            selected_default,
        )
        settings.default_provider = selected_default

    bot = create_bot(settings.bot_token, settings.proxy_url)
    dp = Dispatcher(
        db=db, settings=settings, providers_map=providers_map, provider_registry=provider_registry
    )
    for router in (
        start.router,
        menu.router,
        providers.router,
        search.router,
        favorites.router,
        admin.router,
    ):
        dp.include_router(router)
    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()
        await provider_registry.close()


if __name__ == "__main__":
    asyncio.run(main())
