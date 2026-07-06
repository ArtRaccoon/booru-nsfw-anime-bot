import logging
from collections.abc import Iterable

from aiogram import Bot
from aiogram.types import (
    BotCommand,
    BotCommandScopeAllPrivateChats,
    BotCommandScopeDefault,
    MenuButtonCommands,
)

logger = logging.getLogger(__name__)

BOT_COMMANDS: tuple[BotCommand, ...] = (
    BotCommand(command="start", description="Открыть меню"),
    BotCommand(command="random", description="Случайный арт"),
    BotCommand(command="search", description="Поиск по тегам"),
    BotCommand(command="providers", description="Источники"),
    BotCommand(command="provider", description="Выбрать источник"),
    BotCommand(command="favorites", description="Избранное"),
    BotCommand(command="history", description="История"),
    BotCommand(command="settings", description="Настройки"),
    BotCommand(command="admin", description="Админка"),
    BotCommand(command="stats", description="Статистика"),
    BotCommand(command="help", description="Помощь"),
)

HELP_TEXT = (
    "ℹ️ Помощь\n\n"
    "/start — открыть главное меню и подтвердить 18+.\n"
    "/random — показать случайный арт.\n"
    "/search rating:explicit long_hair — поиск по тегам.\n"
    "/providers — список доступных источников.\n"
    "/favorites — избранные арты.\n"
    "/history — история поисков."
)


def _command_scopes() -> Iterable[BotCommandScopeDefault | BotCommandScopeAllPrivateChats]:
    yield BotCommandScopeDefault()
    yield BotCommandScopeAllPrivateChats()


async def setup_telegram_ui(bot: Bot) -> None:
    """Synchronize Telegram command list and command menu without blocking startup."""
    for scope in _command_scopes():
        try:
            await bot.set_my_commands(list(BOT_COMMANDS), scope=scope)
        except Exception as exc:
            logger.warning(
                "Failed to set Telegram bot commands for scope %s: %s",
                scope.__class__.__name__,
                exc,
            )

    try:
        await bot.set_chat_menu_button(menu_button=MenuButtonCommands())
    except Exception as exc:
        logger.warning("Failed to set Telegram bot menu button: %s", exc)
