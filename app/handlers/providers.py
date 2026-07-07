from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from app.keyboards import providers_keyboard
from app.safety import is_admin
from app.ui.texts import UNKNOWN_PROVIDER

router = Router()


def _arg(message: Message) -> str:
    return message.text.split(maxsplit=1)[1].strip() if len(message.text.split()) > 1 else ""


def format_provider_info(cfg, enabled: bool) -> str:
    return (
        f"{cfg.name} ({cfg.slug})\n"
        f"Engine: {cfg.engine}\nURL: {cfg.base_url}\n"
        f"SFW status: {cfg.sfw_status}\nCategory: {cfg.category}\n"
        f"Enabled: {'yes' if enabled else 'no'}\n"
        f"Default: {'yes' if cfg.enabled_by_default else 'no'}\n"
        f"Requires auth: {'yes' if cfg.requires_auth else 'no'}\n"
        f"Broken: {'yes' if cfg.broken else 'no'}\n"
        f"Anime relevant: {'yes' if cfg.anime_relevant else 'no'}\nNotes: {cfg.notes or '-'}"
    )


async def show_providers(
    target, db, settings, providers_map, provider_registry, page: int = 0
) -> None:
    selected = await db.get_provider(target.from_user.id, settings.default_provider)
    admin = is_admin(target.from_user.id, settings.admin_ids)
    slugs = sorted(provider_registry.configs if admin else providers_map)
    text = "🧭 Источники\nВыбери источник:"
    markup = providers_keyboard(slugs, selected, page, include_disabled=admin)
    await target.answer(text, reply_markup=markup)


@router.message(Command("providers"))
async def providers(message: Message, db, settings, providers_map, provider_registry) -> None:
    await show_providers(message, db, settings, providers_map, provider_registry)


@router.callback_query(lambda c: c.data and c.data.startswith("providers_page:"))
async def providers_page(
    callback: CallbackQuery, db, settings, providers_map, provider_registry
) -> None:
    page = int(callback.data.rsplit(":", 1)[1])
    selected = await db.get_provider(callback.from_user.id, settings.default_provider)
    admin = is_admin(callback.from_user.id, settings.admin_ids)
    slugs = sorted(provider_registry.configs if admin else providers_map)
    await callback.message.edit_text(
        "🧭 Источники\nВыбери источник:",
        reply_markup=providers_keyboard(slugs, selected, page, include_disabled=admin),
    )
    await callback.answer()


@router.message(Command("provider"))
@router.message(Command("set_provider"))
async def set_provider(message: Message, db, providers_map) -> None:
    provider = _arg(message)
    if provider not in providers_map:
        await message.answer(UNKNOWN_PROVIDER)
        return
    await db.set_provider(message.from_user.id, provider)
    await message.answer(f"Источник выбран: {provider}")


@router.message(Command("provider_info"))
async def provider_info(message: Message, provider_registry) -> None:
    slug = _arg(message)
    cfg = provider_registry.configs.get(slug)
    if not cfg:
        await message.answer("Такого источника нет.")
        return
    await message.answer(format_provider_info(cfg, slug in provider_registry.providers))


@router.callback_query(lambda c: c.data and c.data.startswith("provider:"))
async def provider_callback(callback: CallbackQuery, db, providers_map) -> None:
    provider = callback.data.split(":", 1)[1]
    if provider not in providers_map:
        await callback.answer(UNKNOWN_PROVIDER, show_alert=True)
        return
    await db.set_provider(callback.from_user.id, provider)
    await callback.message.edit_text(f"Источник выбран: {provider}")
    await callback.answer()


@router.message(Command("source_mode"))
async def source_mode_cmd(message: Message, db) -> None:
    mode = message.text.split(maxsplit=1)[1].strip() if len(message.text.split()) > 1 else ""
    if mode not in {"selected", "rotation", "fallback"}:
        await message.answer("Использование: /source_mode selected|rotation|fallback")
        return
    await db.set_user_provider_mode(message.from_user.id, mode)
    await message.answer(f"Режим источников: {mode}")


@router.callback_query(F.data == "source_mode_menu")
async def source_mode_menu(callback: CallbackQuery) -> None:
    from app.keyboards import source_mode_keyboard

    await callback.message.edit_text("🌐 Режим источников", reply_markup=source_mode_keyboard())


@router.callback_query(F.data.startswith("source_mode:"))
async def source_mode_pick(callback: CallbackQuery, db) -> None:
    mode = callback.data.split(":", 1)[1]
    await db.set_user_provider_mode(callback.from_user.id, mode)
    await callback.message.edit_text(f"Режим источников: {mode}")
