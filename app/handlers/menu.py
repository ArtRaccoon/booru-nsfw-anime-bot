from aiogram import Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from app.keyboards import admin_keyboard, group_posting_keyboard, settings_keyboard
from app.safety import is_admin

router = Router()


def settings_text(provider: str, confirmed: bool, daily_limit: int, rate_limit_seconds: int) -> str:
    return (
        "⚙️ Настройки\n"
        f"Текущий источник: {provider}\n"
        f"Дневной лимит: {daily_limit}\n"
        f"Кулдаун: {rate_limit_seconds} сек.\n"
        f"18+: {'подтверждено' if confirmed else 'не подтверждено'}"
    )


@router.callback_query(lambda c: c.data == "settings")
async def settings_menu(callback: CallbackQuery, db, settings) -> None:
    provider = await db.get_provider(callback.from_user.id, settings.default_provider)
    confirmed = await db.is_confirmed(callback.from_user.id)
    text = settings_text(provider, confirmed, settings.daily_limit, settings.rate_limit_seconds)
    await callback.message.edit_text(text, reply_markup=settings_keyboard())
    await callback.answer()


@router.message(Command("settings"))
async def settings_command(message: Message, db, settings) -> None:
    provider = await db.get_provider(message.from_user.id, settings.default_provider)
    confirmed = await db.is_confirmed(message.from_user.id)
    await message.answer(
        settings_text(provider, confirmed, settings.daily_limit, settings.rate_limit_seconds),
        reply_markup=settings_keyboard(),
    )


@router.callback_query(lambda c: c.data == "clear_history")
async def clear_history(callback: CallbackQuery, db) -> None:
    await db.clear_history(callback.from_user.id)
    await callback.answer("История очищена.", show_alert=True)


@router.callback_query(lambda c: c.data == "admin_menu")
async def admin_menu(callback: CallbackQuery, settings) -> None:
    if not is_admin(callback.from_user.id, settings.admin_ids):
        await callback.answer("Только для админа.", show_alert=True)
        return
    await callback.message.edit_text("🛠 Админка", reply_markup=admin_keyboard())
    await callback.answer()


@router.callback_query(lambda c: c.data == "admin_stats")
async def admin_stats(callback: CallbackQuery, db, settings) -> None:
    if not is_admin(callback.from_user.id, settings.admin_ids):
        await callback.answer("Только для админа.", show_alert=True)
        return
    data = await db.get_stats()
    await callback.message.answer(
        "📊 Статистика\n"
        f"Пользователи: {data['users']}\n"
        f"Избранное: {data['favorites']}\n"
        f"Поиски: {data['searches']}"
    )
    await callback.answer()


@router.callback_query(lambda c: c.data == "reload_providers")
async def reload_providers_button(
    callback: CallbackQuery, settings, provider_registry, providers_map
) -> None:
    if not is_admin(callback.from_user.id, settings.admin_ids):
        await callback.answer("Только для админа.", show_alert=True)
        return
    await provider_registry.reload()
    providers_map.clear()
    providers_map.update(provider_registry.providers)
    await callback.answer("Источники перезагружены.", show_alert=True)


@router.callback_query(lambda c: c.data and c.data.startswith("admin_providers:"))
async def admin_provider_filter(callback: CallbackQuery, settings, provider_registry) -> None:
    if not is_admin(callback.from_user.id, settings.admin_ids):
        await callback.answer("Только для админа.", show_alert=True)
        return
    kind = callback.data.split(":", 1)[1]
    if kind == "broken":
        slugs = [s for s, cfg in provider_registry.configs.items() if cfg.broken]
        title = "💥 Сломанные"
    elif kind == "auth":
        slugs = [s for s, cfg in provider_registry.configs.items() if cfg.requires_auth]
        title = "🧩 Требуют авторизацию"
    elif kind == "disabled":
        slugs = [s for s in provider_registry.configs if s not in provider_registry.providers]
        title = "💤 Отключённые"
    else:
        slugs = list(provider_registry.providers)
        title = "✅ Активные"
    text = title + "\n" + ("\n".join(sorted(slugs)[:80]) or "Нет")
    await callback.message.answer(text)
    await callback.answer()


@router.callback_query(
    lambda c: c.data in {"admin_test_provider", "admin_enable_provider", "admin_disable_provider"}
)
async def admin_placeholders(callback: CallbackQuery) -> None:
    await callback.answer("Используй соответствующую команду с slug источника.", show_alert=True)


@router.callback_query(lambda c: c.data == "admin_tag_stats")
async def admin_tag_stats_button(callback: CallbackQuery, db, settings) -> None:
    if not is_admin(callback.from_user.id, settings.admin_ids):
        await callback.answer("Только для админа.", show_alert=True)
        return
    rows = await db.top_tags(30)
    text = "\n".join(f"{r['tag']}: {r['count']}" for r in rows) or "Нет данных."
    await callback.message.answer("🏷 Топ тегов\n" + text)
    await callback.answer()


@router.callback_query(lambda c: c.data in {"admin_user_tags", "admin_user_searches"})
async def admin_stats_help(callback: CallbackQuery, settings) -> None:
    if not is_admin(callback.from_user.id, settings.admin_ids):
        await callback.answer("Только для админа.", show_alert=True)
        return
    await callback.answer(
        "Используй /tag_stats_user <telegram_id> или /user_searches <telegram_id>.", show_alert=True
    )


@router.callback_query(lambda c: c.data == "admin_group_posting")
async def admin_group_posting(callback: CallbackQuery, settings) -> None:
    if not is_admin(callback.from_user.id, settings.admin_ids):
        await callback.answer("Только для админа.", show_alert=True)
        return
    await callback.message.edit_text("🛰 Групповой постинг", reply_markup=group_posting_keyboard())
    await callback.answer()


@router.callback_query(lambda c: c.data and c.data.endswith("_help"))
async def group_help(callback: CallbackQuery, settings) -> None:
    if not is_admin(callback.from_user.id, settings.admin_ids):
        await callback.answer("Только для админа.", show_alert=True)
        return
    commands = {
        "group_bind_help": "/group_bind <chat_id>",
        "group_enable_help": "/group_enable",
        "group_disable_help": "/group_disable",
        "group_mode_help": "/group_mode sfw|nsfw|mixed",
        "group_tags_help": "/group_tags <tags>",
        "group_interval_help": "/group_interval <minutes>",
        "group_post_now_help": "/group_post_now",
        "group_history_help": "/group_history",
    }
    await callback.answer(commands.get(callback.data, "Команда недоступна"), show_alert=True)
