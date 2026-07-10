from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.types import CallbackQuery, InputMediaPhoto

from app.keyboards import (
    random_art_keyboard,
    random_empty_keyboard,
    random_tags_keyboard,
)
from app.loading import show_loading
from app.random_art import (
    FIRST_ART_TEXT,
    INITIAL_EMPTY_ART_TEXT,
    NO_UNIQUE_ART_TEXT,
    RANDOM_TITLE,
    SAVE_DUPLICATE_NOTIFICATION_TEXT,
    SAVE_SUCCESS_NOTIFICATION_TEXT,
    RandomArtService,
    format_tags_text,
)

router = Router()
random_art_service = RandomArtService()


def _user_id(call: CallbackQuery) -> int | None:
    return call.from_user.id if call.from_user else None


async def _show_artwork(call: CallbackQuery, *, send_new: bool) -> None:
    user_id = _user_id(call)
    if user_id is None:
        await call.answer()
        return
    artwork = random_art_service.gallery(user_id).current
    if artwork is None:
        await call.answer(NO_UNIQUE_ART_TEXT)
        return
    if send_new:
        if call.message:
            await call.message.answer_photo(
                artwork.file_url, caption=RANDOM_TITLE, reply_markup=random_art_keyboard()
            )
    elif call.message:
        await call.message.edit_media(
            InputMediaPhoto(media=artwork.file_url, caption=RANDOM_TITLE),
            reply_markup=random_art_keyboard(),
        )
    await call.answer()


@router.callback_query(F.data == "menu:random")
async def random_open(call: CallbackQuery) -> None:
    user_id = _user_id(call)
    if user_id is None:
        await call.answer()
        return
    await show_loading(call)
    artwork = await random_art_service.next_artwork(user_id)
    if artwork is None:
        logging.info("initial random empty (%s)", user_id)
        if call.message:
            await call.message.edit_text(
                INITIAL_EMPTY_ART_TEXT,
                reply_markup=random_empty_keyboard(),
            )
        await call.answer()
        return
    if call.message:
        await call.message.edit_text(RANDOM_TITLE)
    await _show_artwork(call, send_new=True)


@router.callback_query(F.data == "random:next")
async def random_next(call: CallbackQuery) -> None:
    user_id = _user_id(call)
    if user_id is None:
        await call.answer()
        return
    artwork = random_art_service.next_from_history(user_id)
    if artwork is None:
        artwork = await random_art_service.next_artwork(user_id)
    if artwork is None:
        await call.answer(NO_UNIQUE_ART_TEXT)
        return
    await show_loading(call)
    await _show_artwork(call, send_new=False)


@router.callback_query(F.data == "random:previous")
async def random_previous(call: CallbackQuery) -> None:
    user_id = _user_id(call)
    if user_id is None:
        await call.answer()
        return
    artwork = random_art_service.previous_artwork(user_id)
    if artwork is None:
        await call.answer(FIRST_ART_TEXT)
        return
    await show_loading(call)
    await _show_artwork(call, send_new=False)


@router.callback_query(F.data == "random:save")
async def random_save(call: CallbackQuery) -> None:
    user_id = _user_id(call)
    if user_id is None:
        await call.answer()
        return
    if random_art_service.save_current(user_id):
        logging.info("favorite saved notification (%s)", user_id)
        await call.answer(SAVE_SUCCESS_NOTIFICATION_TEXT)
    else:
        logging.info("favorite duplicate notification (%s)", user_id)
        await call.answer(SAVE_DUPLICATE_NOTIFICATION_TEXT)


@router.callback_query(F.data == "random:tags")
async def random_tags(call: CallbackQuery) -> None:
    user_id = _user_id(call)
    if user_id is None:
        await call.answer()
        return
    artwork = random_art_service.gallery(user_id).current
    if artwork is None:
        await call.answer(NO_UNIQUE_ART_TEXT)
        return
    logging.info("tags shown (%s:%s, %s)", *artwork.unique_key, user_id)
    if call.message:
        await call.message.edit_caption(
            caption=format_tags_text(artwork),
            parse_mode="HTML",
            reply_markup=random_tags_keyboard(),
        )
    await call.answer()


@router.callback_query(F.data == "random:artwork")
async def random_artwork(call: CallbackQuery) -> None:
    user_id = _user_id(call)
    if user_id is None:
        await call.answer()
        return
    artwork = random_art_service.gallery(user_id).current
    if artwork:
        logging.info("returned to artwork (%s:%s, %s)", *artwork.unique_key, user_id)
    await show_loading(call)
    await _show_artwork(call, send_new=False)


@router.callback_query(F.data == "random:main")
async def random_main_menu(call: CallbackQuery) -> None:
    from app.handlers.start import render_main_menu

    user_id = _user_id(call)
    logging.info("random main menu clicked (%s)", user_id)
    await render_main_menu(call, user_id)
    logging.info("random main menu returned (%s)", user_id)
    await call.answer()
