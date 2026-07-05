from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import CallbackQuery, Message

from app.keyboards import age_gate_keyboard

router = Router()


@router.message(CommandStart())
async def start(message: Message, db) -> None:
    await db.upsert_user(message.from_user.id, message.from_user.username)
    await message.answer(
        "This bot returns adult NSFW anime images. Confirm you are 18+ to continue.",
        reply_markup=age_gate_keyboard(),
    )


@router.callback_query(lambda c: c.data == "age:confirm")
async def confirm_age(callback: CallbackQuery, db) -> None:
    await db.confirm_adult(callback.from_user.id)
    await callback.message.edit_text("Confirmed. Use /search <tags>, /random, or /providers.")
