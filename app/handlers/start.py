from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.types import CallbackQuery, Message

from app.keyboards import search_keyboard

router = Router()

START_TEXT = (
    "🦝 Енот Ищейка\n\n"
    "Добро пожаловать в логово самого любопытного енота.\n"
    "Я умею вынюхивать арты, находить редкие иллюстрации, искать по тегам, "
    "авторам и персонажам, а ещё собирать изображения из множества художественных архивов.\n\n"
    "✨ Просто дай мне след, а остальное я раскопаю сама.\n\n"
    "⬇️ Нажми кнопку ниже, чтобы начать поиск."
)

SEARCH_UNDER_CONSTRUCTION_TEXT = "🚧 Поиск пока находится в разработке."


def _user_id(event: Message | CallbackQuery) -> int | None:
    return event.from_user.id if event.from_user else None


@router.message(CommandStart())
async def start(message: Message) -> None:
    logging.info("/start opened (%s)", _user_id(message))
    await message.answer(START_TEXT, reply_markup=search_keyboard())


@router.callback_query(F.data == "search:start")
async def search_start(call: CallbackQuery) -> None:
    logging.info("search:start clicked (%s)", _user_id(call))
    await call.answer(SEARCH_UNDER_CONSTRUCTION_TEXT)
