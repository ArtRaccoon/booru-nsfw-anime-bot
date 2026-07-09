from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import CommandStart
from aiogram.types import CallbackQuery, Message, PreCheckoutQuery

from app.keyboards import (
    main_menu_keyboard,
    premium_keyboard,
    search_keyboard,
    search_prompt_keyboard,
    search_results_keyboard,
)
from app.premium import (
    PREMIUM_PLANS,
    TelegramStarsInvoiceService,
    activate_pending_premium,
    premium_payload,
    store_pending_premium_plan,
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
PREMIUM_TEXT = (
    "🦝 Енот Ищейка Premium\n\n"
    "Премиум открывает взрослый режим поиска:\n\n"
    "🔞 NSFW поиск по тегам\n"
    "🎲 NSFW случайные арты\n"
    "🏷 больше возможностей для фильтрации\n\n"
    "Выбери срок доступа:"
)
PREMIUM_ACTIVATED_TEXT = "Премиум активирован 💎"
MENU_PREMIUM_TEXT = PREMIUM_TEXT

premium_invoice_service = TelegramStarsInvoiceService()

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


@router.callback_query(F.data == "menu:premium")
async def premium_open(call: CallbackQuery) -> None:
    logging.info("premium opened (%s)", _user_id(call))
    if call.message:
        await call.message.edit_text(PREMIUM_TEXT, reply_markup=premium_keyboard())
    await call.answer()


@router.callback_query(F.data == "premium:main")
async def premium_main_menu(call: CallbackQuery) -> None:
    await _show_main_menu(call)
    logging.info("premium returned to main menu (%s)", _user_id(call))
    await call.answer()


@router.callback_query(F.data.in_({"premium:day", "premium:week", "premium:month"}))
async def premium_plan_selected(call: CallbackQuery) -> None:
    user_id = _user_id(call)
    if user_id is None or call.data is None:
        await call.answer()
        return

    plan_code = call.data.split(":", 1)[1]
    plan = PREMIUM_PLANS[plan_code]
    payload = premium_payload(user_id, plan_code)
    store_pending_premium_plan(user_id, plan_code, payload)
    await premium_invoice_service.create_invoice(call.bot, user_id, plan, payload)
    logging.info("premium invoice created (%s): %s", user_id, plan_code)
    await call.answer()


@router.pre_checkout_query()
async def premium_pre_checkout(pre_checkout_query: PreCheckoutQuery) -> None:
    await pre_checkout_query.answer(ok=True)


@router.message(F.successful_payment)
async def premium_successful_payment(message: Message) -> None:
    user_id = _user_id(message)
    if user_id is None or message.successful_payment is None:
        return
    activate_pending_premium(message.successful_payment.invoice_payload, user_id)
    logging.info("premium activated (%s)", user_id)
    await message.answer(PREMIUM_ACTIVATED_TEXT)


async def main_menu_stub(call: CallbackQuery) -> None:
    await premium_open(call)
