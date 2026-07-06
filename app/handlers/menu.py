from aiogram import Router
from aiogram.types import CallbackQuery

from app.keyboards import admin_keyboard, settings_keyboard
from app.safety import is_admin

router = Router()


@router.callback_query(lambda c: c.data == "settings")
async def settings_menu(callback: CallbackQuery, db, settings) -> None:
    provider = await db.get_provider(callback.from_user.id, settings.default_provider)
    confirmed = await db.is_confirmed(callback.from_user.id)
    text = (
        "⚙️ Настройки\n"
        f"Текущий источник: {provider}\n"
        f"Дневной лимит: {settings.daily_limit}\n"
        f"Кулдаун: {settings.rate_limit_seconds} сек.\n"
        f"18+: {'подтверждено' if confirmed else 'не подтверждено'}"
    )
    await callback.message.edit_text(text, reply_markup=settings_keyboard())
    await callback.answer()


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
