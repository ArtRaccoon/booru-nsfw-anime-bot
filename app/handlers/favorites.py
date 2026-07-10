from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.types import CallbackQuery, InputMediaPhoto

from app.handlers.random_art import random_art_service
from app.keyboards import (
    favorites_art_keyboard,
    favorites_empty_keyboard,
    favorites_tags_keyboard,
)
from app.loading import show_loading
from app.random_art import RANDOM_TITLE, Artwork, format_tags_text

router = Router()

EMPTY_FAVORITES_TEXT = (
    "🦝 Енот Ищейка\n\n"
    "В избранном пока пусто.\n"
    "Сначала сохрани пару артов, а потом я аккуратно сложу их сюда."
)
FIRST_FAVORITE_TEXT = "Это первый сохранённый арт."
LAST_FAVORITE_TEXT = "Это последний сохранённый арт."
DELETE_FAVORITE_TEXT = "Удалено из избранного"

favorites_index: dict[int, int] = {}


def _user_id(call: CallbackQuery) -> int | None:
    return call.from_user.id if call.from_user else None


def _favorites(user_id: int) -> list[Artwork]:
    return random_art_service.favorite_artworks(user_id)


def _clamp_index(user_id: int, favorites: list[Artwork]) -> int:
    if not favorites:
        favorites_index[user_id] = 0
        return 0
    index = favorites_index.get(user_id, 0)
    index = max(0, min(index, len(favorites) - 1))
    favorites_index[user_id] = index
    return index


async def _show_empty(call: CallbackQuery) -> None:
    if call.message:
        await call.message.edit_text(EMPTY_FAVORITES_TEXT, reply_markup=favorites_empty_keyboard())


async def _show_artwork(call: CallbackQuery) -> None:
    user_id = _user_id(call)
    if user_id is None:
        return
    favorites = _favorites(user_id)
    if not favorites:
        await _show_empty(call)
        return
    artwork = favorites[_clamp_index(user_id, favorites)]
    if call.message:
        await call.message.edit_media(
            InputMediaPhoto(media=artwork.file_url, caption=RANDOM_TITLE),
            reply_markup=favorites_art_keyboard(),
        )
    logging.info("favorites shown (%s:%s, %s)", *artwork.unique_key, user_id)


@router.callback_query(F.data == "menu:favorites")
async def favorites_open(call: CallbackQuery) -> None:
    user_id = _user_id(call)
    logging.info("favorites opened (%s)", user_id)
    if user_id is None:
        await call.answer()
        return
    await show_loading(call)
    favorites_index[user_id] = 0
    favorites = _favorites(user_id)
    if not favorites:
        logging.info("favorites empty (%s)", user_id)
        await _show_empty(call)
        await call.answer()
        return
    if call.message:
        await call.message.edit_text(RANDOM_TITLE)
        artwork = favorites[0]
        await call.message.answer_photo(
            artwork.file_url, caption=RANDOM_TITLE, reply_markup=favorites_art_keyboard()
        )
        logging.info("favorites shown (%s:%s, %s)", *artwork.unique_key, user_id)
    await call.answer()


@router.callback_query(F.data == "favorites:next")
async def favorites_next(call: CallbackQuery) -> None:
    user_id = _user_id(call)
    if user_id is None:
        await call.answer()
        return
    favorites = _favorites(user_id)
    index = _clamp_index(user_id, favorites)
    if index >= len(favorites) - 1:
        logging.info("favorites last boundary (%s)", user_id)
        await call.answer(LAST_FAVORITE_TEXT)
        return
    favorites_index[user_id] = index + 1
    logging.info("favorites next (%s)", user_id)
    await show_loading(call)
    await _show_artwork(call)
    await call.answer()


@router.callback_query(F.data == "favorites:previous")
async def favorites_previous(call: CallbackQuery) -> None:
    user_id = _user_id(call)
    if user_id is None:
        await call.answer()
        return
    favorites = _favorites(user_id)
    index = _clamp_index(user_id, favorites)
    if index <= 0:
        logging.info("favorites first boundary (%s)", user_id)
        await call.answer(FIRST_FAVORITE_TEXT)
        return
    favorites_index[user_id] = index - 1
    logging.info("favorites previous (%s)", user_id)
    await show_loading(call)
    await _show_artwork(call)
    await call.answer()


@router.callback_query(F.data == "favorites:delete")
async def favorites_delete(call: CallbackQuery) -> None:
    user_id = _user_id(call)
    if user_id is None:
        await call.answer()
        return
    index = _clamp_index(user_id, _favorites(user_id))
    random_art_service.delete_favorite(user_id, index)
    logging.info("favorite deleted (%s)", user_id)
    await call.answer(DELETE_FAVORITE_TEXT)
    favorites = _favorites(user_id)
    if not favorites:
        logging.info("favorites empty (%s)", user_id)
        await _show_empty(call)
        return
    favorites_index[user_id] = min(index, len(favorites) - 1)
    await _show_artwork(call)


@router.callback_query(F.data == "favorites:tags")
async def favorites_tags(call: CallbackQuery) -> None:
    user_id = _user_id(call)
    if user_id is None:
        await call.answer()
        return
    favorites = _favorites(user_id)
    if not favorites:
        await _show_empty(call)
        await call.answer()
        return
    artwork = favorites[_clamp_index(user_id, favorites)]
    logging.info("favorites tags shown (%s:%s, %s)", *artwork.unique_key, user_id)
    if call.message:
        await call.message.edit_caption(
            caption=format_tags_text(artwork),
            parse_mode="HTML",
            reply_markup=favorites_tags_keyboard(),
        )
    await call.answer()


@router.callback_query(F.data == "favorites:artwork")
async def favorites_artwork(call: CallbackQuery) -> None:
    user_id = _user_id(call)
    logging.info("favorites returned to artwork (%s)", user_id)
    await show_loading(call)
    await _show_artwork(call)
    await call.answer()


@router.callback_query(F.data == "favorites:main")
async def favorites_main(call: CallbackQuery) -> None:
    from app.handlers.start import render_main_menu

    user_id = _user_id(call)
    logging.info("favorites returned to main menu (%s)", user_id)
    await render_main_menu(call, user_id)
    await call.answer()
