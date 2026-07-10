from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Sequence
from typing import TypeVar

from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery, Message

LOADING_FRAMES = (
    "🐾 Енот взял след…",
    "🗃 Перебираю архивы…",
    "🔍 Проверяю находку…",
    "✨ Кажется, нашла…",
)
_LOADING_FALLBACK_TEXT = "Ищу арт…"
_FRAME_DELAY_SECONDS = 1.2
_FINAL_FRAME_SECONDS = 0.8
_MIN_VISIBLE_SECONDS = 3.0
_TARGET_VISIBLE_SECONDS = 5.0

T = TypeVar("T")


async def _safe_answer_callback(
    callback: CallbackQuery, text: str | None = None
) -> None:
    try:
        await callback.answer(text)
    except TelegramBadRequest as error:
        logging.info("loading callback answer skipped: %s", error)


async def _delete_loading_message(message: Message | None, user_id: int | None) -> None:
    if message is None:
        return
    try:
        await message.delete()
        logging.info("loading message deleted (%s)", user_id)
    except TelegramBadRequest as error:
        logging.info("loading delete skipped (%s): %s", user_id, error)


async def _animate_message(
    loading_message: Message,
    *,
    user_id: int | None,
    done: asyncio.Event | None = None,
    frames: Sequence[str] | None = None,
) -> None:
    active_frames = tuple(frames or LOADING_FRAMES)
    if not active_frames:
        return

    for frame in active_frames[1:]:
        await asyncio.sleep(_FRAME_DELAY_SECONDS)
        try:
            await loading_message.edit_text(frame)
            logging.info("loading frame updated (%s): text", user_id)
        except TelegramBadRequest as error:
            logging.info("loading frame edit failed (%s): %s", user_id, error)
            return

    if done is None:
        await asyncio.sleep(_FINAL_FRAME_SECONDS)
        return

    while not done.is_set():
        await asyncio.sleep(_FINAL_FRAME_SECONDS)


async def show_loading(
    callback: CallbackQuery, *, frames: Sequence[str] | None = None
) -> Message | None:
    """Show and remove a temporary callback loading message without editing artwork."""
    user_id = callback.from_user.id if callback.from_user else None
    active_frames = tuple(frames or LOADING_FRAMES)
    logging.info("loading started (%s)", user_id)
    loading_message: Message | None = None
    try:
        await _safe_answer_callback(callback)
        if callback.message is None or not active_frames:
            logging.info("loading frame skipped (%s): no message", user_id)
            return None
        loading_message = await callback.message.answer(active_frames[0])
        logging.info("loading frame updated (%s): text", user_id)
        await _animate_message(loading_message, user_id=user_id, frames=active_frames)
        return loading_message
    except TelegramBadRequest as error:
        logging.info("loading frame edit failed (%s): %s", user_id, error)
        if loading_message is None:
            await _safe_answer_callback(callback, _LOADING_FALLBACK_TEXT)
        return loading_message
    finally:
        await _delete_loading_message(loading_message, user_id)
        logging.info("loading finished (%s)", user_id)


async def show_loading_while(
    callback: CallbackQuery,
    work: Awaitable[T],
    *,
    frames: Sequence[str] | None = None,
) -> T:
    """Answer callback, animate one temporary message, and return prepared work result."""
    user_id = callback.from_user.id if callback.from_user else None
    active_frames = tuple(frames or LOADING_FRAMES)
    logging.info("loading started (%s)", user_id)
    await _safe_answer_callback(callback)

    loading_message: Message | None = None
    done = asyncio.Event()
    started = time.monotonic()
    work_task = asyncio.create_task(work)
    animation_task: asyncio.Task[None] | None = None
    try:
        if callback.message is not None and active_frames:
            loading_message = await callback.message.answer(active_frames[0])
            logging.info("loading frame updated (%s): text", user_id)
            animation_task = asyncio.create_task(
                _animate_message(
                    loading_message, user_id=user_id, done=done, frames=active_frames
                )
            )
        result = await work_task
        elapsed = time.monotonic() - started
        minimum = (
            _TARGET_VISIBLE_SECONDS
            if elapsed < _TARGET_VISIBLE_SECONDS
            else _MIN_VISIBLE_SECONDS
        )
        if elapsed < minimum:
            await asyncio.sleep(minimum - elapsed)
        return result
    finally:
        done.set()
        if animation_task is not None:
            await animation_task
        await _delete_loading_message(loading_message, user_id)
        logging.info("loading finished (%s)", user_id)


async def show_message_loading(
    message: Message, *, frames: Sequence[str] | None = None
) -> Message | None:
    """Send a short-lived loading message for non-callback artwork actions."""
    loading_message = await message.answer(tuple(frames or LOADING_FRAMES)[0])
    await _animate_message(
        loading_message,
        user_id=message.from_user.id if message.from_user else None,
        frames=frames,
    )
    return loading_message
