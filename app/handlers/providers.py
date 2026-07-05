from aiogram import Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from app.keyboards import providers_keyboard

router = Router()


@router.message(Command("providers"))
async def providers(message: Message, providers_map) -> None:
    await message.answer("Choose provider:", reply_markup=providers_keyboard(list(providers_map)))


@router.message(Command("set_provider"))
async def set_provider(message: Message, db, providers_map) -> None:
    provider = message.text.split(maxsplit=1)[1].strip() if len(message.text.split()) > 1 else ""
    if provider not in providers_map:
        await message.answer("Unknown provider. Use /providers.")
        return
    await db.set_provider(message.from_user.id, provider)
    await message.answer(f"Provider set to {provider}.")


@router.callback_query(lambda c: c.data.startswith("provider:"))
async def provider_callback(callback: CallbackQuery, db, providers_map) -> None:
    provider = callback.data.split(":", 1)[1]
    if provider in providers_map:
        await db.set_provider(callback.from_user.id, provider)
        await callback.message.edit_text(f"Provider set to {provider}.")
