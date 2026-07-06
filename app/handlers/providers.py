from aiogram import Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from app.keyboards import providers_keyboard

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


@router.message(Command("providers"))
async def providers(message: Message, providers_map) -> None:
    await message.answer("Choose provider:", reply_markup=providers_keyboard(list(providers_map)))


@router.message(Command("provider"))
@router.message(Command("set_provider"))
async def set_provider(message: Message, db, providers_map) -> None:
    provider = _arg(message)
    if provider not in providers_map:
        await message.answer("Unknown or disabled provider. Use /providers.")
        return
    await db.set_provider(message.from_user.id, provider)
    await message.answer(f"Provider set to {provider}.")


@router.message(Command("provider_info"))
async def provider_info(message: Message, provider_registry) -> None:
    slug = _arg(message)
    cfg = provider_registry.configs.get(slug)
    if not cfg:
        await message.answer("Unknown provider.")
        return
    await message.answer(format_provider_info(cfg, slug in provider_registry.providers))


@router.callback_query(lambda c: c.data.startswith("provider:"))
async def provider_callback(callback: CallbackQuery, db, providers_map) -> None:
    provider = callback.data.split(":", 1)[1]
    if provider in providers_map:
        await db.set_provider(callback.from_user.id, provider)
        await callback.message.edit_text(f"Provider set to {provider}.")
