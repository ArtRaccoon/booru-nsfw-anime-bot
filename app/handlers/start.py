from __future__ import annotations

import logging
from contextlib import suppress

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import CommandStart
from aiogram.types import CallbackQuery, InputMediaPhoto, Message, PreCheckoutQuery

from app.handlers.random_art import random_art_service
from app.keyboards import (
    main_menu_keyboard,
    premium_keyboard,
    search_keyboard,
    search_prompt_keyboard,
    search_results_keyboard,
    search_tags_keyboard,
)
from app.loading import show_loading, show_message_loading
from app.premium import (
    PREMIUM_PLANS,
    TelegramStarsInvoiceService,
    activate_pending_premium,
    premium_payload,
    store_pending_premium_plan,
)
from app.random_art import (
    FIRST_ART_TEXT,
    NO_UNIQUE_ART_TEXT,
    RANDOM_TITLE,
    SAVE_DUPLICATE_NOTIFICATION_TEXT,
    SAVE_SUCCESS_NOTIFICATION_TEXT,
    format_tags_text,
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


def clear_transient_user_state(user_id: int | None) -> None:
    if user_id is None:
        return
    search_user_states.pop(user_id, None)
    logging.info("transient state cleared (%s)", user_id)


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
    return "🦝 Енот Ищейка\n\n" + ", ".join(tags)


async def render_main_menu(target: CallbackQuery | Message, user_id: int | None) -> None:
    clear_transient_user_state(user_id)
    message = target.message if hasattr(target, "message") else target
    if message is None:
        return
    try:
        await message.edit_text(MAIN_MENU_TEXT, reply_markup=main_menu_keyboard())
    except TelegramBadRequest as error:
        logging.info("main menu text edit failed (%s): %s", user_id, error)
        try:
            await message.edit_caption(
                caption=MAIN_MENU_TEXT,
                reply_markup=main_menu_keyboard(),
            )
            return
        except TelegramBadRequest as caption_error:
            logging.info("main menu caption edit failed (%s): %s", user_id, caption_error)
        try:
            await message.delete()
        except TelegramBadRequest as delete_error:
            logging.info("main menu stale message delete skipped (%s): %s", user_id, delete_error)
        await message.answer(MAIN_MENU_TEXT, reply_markup=main_menu_keyboard())


async def _show_main_menu(call: CallbackQuery) -> None:
    await render_main_menu(call, _user_id(call))


@router.message(CommandStart())
async def start(message: Message) -> None:
    user_id = _user_id(message)
    clear_transient_user_state(user_id)
    logging.info("/start opened (%s)", user_id)
    await message.answer(START_TEXT, reply_markup=search_keyboard())


@router.callback_query(F.data == "search:start")
async def search_start(call: CallbackQuery) -> None:
    logging.info("search:start clicked (%s)", _user_id(call))
    await render_main_menu(call, _user_id(call))
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

    loading_message = await show_message_loading(message)
    artwork = await random_art_service.start_search(user_id, tags)
    if loading_message is not None:
        with suppress(TelegramBadRequest):
            await loading_message.delete()
    if artwork is None:
        await message.answer("Не нашла арт по этим тегам. Попробуй другие.")
        return
    await message.answer_photo(
        artwork.file_url, caption=RANDOM_TITLE, reply_markup=search_results_keyboard()
    )


async def _show_search_artwork(call: CallbackQuery, *, send_new: bool = False) -> None:
    user_id = _user_id(call)
    session = random_art_service.search_gallery(user_id) if user_id is not None else None
    artwork = session.current if session else None
    if artwork is None:
        await call.answer(NO_UNIQUE_ART_TEXT)
        return
    if send_new and call.message:
        await call.message.answer_photo(
            artwork.file_url, caption=RANDOM_TITLE, reply_markup=search_results_keyboard()
        )
    elif call.message:
        await call.message.edit_media(
            InputMediaPhoto(media=artwork.file_url, caption=RANDOM_TITLE),
            reply_markup=search_results_keyboard(),
        )
    await call.answer()


@router.callback_query(F.data == "search:next")
async def search_next(call: CallbackQuery) -> None:
    user_id = _user_id(call)
    if user_id is None:
        await call.answer()
        return
    artwork = random_art_service.next_search_from_history(user_id)
    if artwork is None:
        artwork = await random_art_service.next_search_artwork(user_id)
    if artwork is None:
        await call.answer(NO_UNIQUE_ART_TEXT)
        return
    await show_loading(call)
    await _show_search_artwork(call)


@router.callback_query(F.data == "search:previous")
async def search_previous(call: CallbackQuery) -> None:
    user_id = _user_id(call)
    if user_id is None:
        await call.answer()
        return
    if random_art_service.previous_search_artwork(user_id) is None:
        await call.answer(FIRST_ART_TEXT)
        return
    await show_loading(call)
    await _show_search_artwork(call)


@router.callback_query(F.data == "search:tags")
async def search_tags(call: CallbackQuery) -> None:
    user_id = _user_id(call)
    session = random_art_service.search_gallery(user_id) if user_id is not None else None
    artwork = session.current if session else None
    if artwork is None:
        await call.answer(NO_UNIQUE_ART_TEXT)
        return
    if call.message:
        await call.message.edit_caption(
            caption=format_tags_text(artwork),
            parse_mode="HTML",
            reply_markup=search_tags_keyboard(),
        )
    await call.answer()


@router.callback_query(F.data == "search:artwork")
async def search_artwork(call: CallbackQuery) -> None:
    await show_loading(call)
    await _show_search_artwork(call)


@router.callback_query(F.data == "search:save")
async def search_save(call: CallbackQuery) -> None:
    user_id = _user_id(call)
    session = random_art_service.search_gallery(user_id) if user_id is not None else None
    artwork = session.current if session else None
    if user_id is None or artwork is None:
        await call.answer(NO_UNIQUE_ART_TEXT)
        return
    gallery = random_art_service.gallery(user_id)
    if artwork.unique_key not in {art.unique_key for art in gallery.history}:
        gallery.history.append(artwork)
        gallery.current_index = len(gallery.history) - 1
    if random_art_service.save_current(user_id):
        await call.answer(SAVE_SUCCESS_NOTIFICATION_TEXT)
    else:
        await call.answer(SAVE_DUPLICATE_NOTIFICATION_TEXT)


@router.callback_query(F.data == "search:main")
async def search_main_menu(call: CallbackQuery) -> None:
    user_id = _user_id(call)
    clear_transient_user_state(user_id)
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
