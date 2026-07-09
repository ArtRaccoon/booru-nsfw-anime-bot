from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import CommandStart
from aiogram.types import CallbackQuery, Message

from app.keyboards import (
    main_menu_keyboard,
    search_keyboard,
    search_prompt_keyboard,
    search_results_keyboard,
)

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

SEARCH_PROMPT_TEXT = (
    "🦝 Енот Ищейка\n\n"
    "Введи тег или несколько тегов через запятую.\n\n"
    "Пример:\n"
    "landscape, sunset, long_hair"
)
SEARCH_WAITING_STATE = "waiting_for_search_tags"
SEARCH_HINT_TEXT = "Открой поиск через меню, и я пойму, что искать."
MENU_RANDOM_TEXT = "🎲 Рандомный арт добавим следующим этапом."
MENU_PREMIUM_TEXT = "💎 Премиум-раздел пока закрыт на маленький енотовый замочек."

MENU_STUBS = {
    "menu:premium": MENU_PREMIUM_TEXT,
}

search_user_states: dict[int, str] = {}


def _user_id(event: Message | CallbackQuery) -> int | None:
    return event.from_user.id if event.from_user else None


def parse_search_tags(text: str) -> list[str]:
    tags: list[str] = []
    for raw_tag in text.split(","):
        tag = "_".join(raw_tag.strip().lower().split())
        if tag:
            tags.append(tag)
    return tags


def format_search_preview_text(tags: list[str]) -> str:
    return (
        "🦝 Енот Ищейка\n\n"
        "Я поняла след:\n\n"
        f"{', '.join(tags)}\n\n"
        "Поиск по тегам добавим следующим этапом."
    )


async def _show_main_menu(call: CallbackQuery) -> None:
    if call.message:
        try:
            await call.message.edit_text(MAIN_MENU_TEXT, reply_markup=main_menu_keyboard())
        except TelegramBadRequest:
            await call.message.answer(MAIN_MENU_TEXT, reply_markup=main_menu_keyboard())


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


@router.callback_query(F.data == "menu:search")
async def search_open(call: CallbackQuery) -> None:
    user_id = _user_id(call)
    if user_id is not None:
        search_user_states[user_id] = SEARCH_WAITING_STATE
    logging.info("search opened (%s)", user_id)
    if call.message:
        await call.message.edit_text(SEARCH_PROMPT_TEXT, reply_markup=search_prompt_keyboard())
    await call.answer()


@router.message(F.text)
async def search_text_received(message: Message) -> None:
    user_id = _user_id(message)
    if user_id is None:
        return
    if search_user_states.get(user_id) != SEARCH_WAITING_STATE:
        await message.answer(SEARCH_HINT_TEXT)
        return

    logging.info("search text received (%s)", user_id)
    tags = parse_search_tags(message.text or "")
    logging.info("search tags parsed (%s): %s", user_id, tags)
    search_user_states.pop(user_id, None)
    logging.info("search state cleared (%s)", user_id)

    await message.answer(format_search_preview_text(tags), reply_markup=search_results_keyboard())


@router.callback_query(F.data == "search:main")
async def search_main_menu(call: CallbackQuery) -> None:
    user_id = _user_id(call)
    if user_id is not None:
        search_user_states.pop(user_id, None)
    await _show_main_menu(call)
    logging.info("search returned to main menu (%s)", user_id)
    await call.answer()


@router.callback_query(F.data.in_(MENU_STUBS))
async def main_menu_stub(call: CallbackQuery) -> None:
    logging.info("%s clicked (%s)", call.data, _user_id(call))
    await call.answer(MENU_STUBS[call.data])
