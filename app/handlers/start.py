from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.types import CallbackQuery, Message

from app.keyboards import main_menu_keyboard, search_keyboard

router = Router()

START_TEXT = (
    "🦝 Енот Ищейка\n\n"
    "Добро пожаловать в логово самого любопытного енота.\n"
    "Я умею вынюхивать арты, находить редкие иллюстрации, искать по тегам, "
    "авторам и персонажам, а ещё собирать изображения из множества художественных архивов.\n\n"
    "✨ Просто дай мне след, а остальное я раскопаю сама.\n\n"
    "⬇️ Нажми кнопку ниже, чтобы начать поиск."
)

MAIN_MENU_TEXT = "🦝 Енот Ищейка уже принюхался.\n\nВыбери, куда пойдём дальше:"

MENU_RANDOM_TEXT = "🎲 Рандомный арт добавим следующим этапом."
MENU_SEARCH_TEXT = "🔎 Поиск по тегам скоро появится."
MENU_PREMIUM_TEXT = "💎 Премиум-раздел пока закрыт на маленький енотовый замочек."

MENU_STUBS = {
    "menu:search": MENU_SEARCH_TEXT,
    "menu:premium": MENU_PREMIUM_TEXT,
}


def _user_id(event: Message | CallbackQuery) -> int | None:
    return event.from_user.id if event.from_user else None


@router.message(CommandStart())
async def start(message: Message) -> None:
    logging.info("/start opened (%s)", _user_id(message))
    await message.answer(START_TEXT, reply_markup=search_keyboard())


@router.callback_query(F.data == "search:start")
async def search_start(call: CallbackQuery) -> None:
    logging.info("search:start clicked (%s)", _user_id(call))
    if call.message:
        await call.message.edit_text(MAIN_MENU_TEXT, reply_markup=main_menu_keyboard())
    logging.info("main menu opened (%s)", _user_id(call))
    await call.answer()


@router.callback_query(F.data.in_(MENU_STUBS))
async def main_menu_stub(call: CallbackQuery) -> None:
    logging.info("%s clicked (%s)", call.data, _user_id(call))
    await call.answer(MENU_STUBS[call.data])
