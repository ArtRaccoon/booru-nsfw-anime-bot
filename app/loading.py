from __future__ import annotations

import asyncio
import logging
from collections.abc import Sequence

from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery, Message

LOADING_FRAMES = (
    "🦝 шур-шур по архивам…",
    "🦝 нюхаю след арта…",
    "🔎 почти нашла…",
)
_LOADING_FALLBACK_TEXT = "Ищу арт…"
_MESSAGE_NOT_MODIFIED = "message is not modified"


def _is_not_modified(error: TelegramBadRequest) -> bool:
    return _MESSAGE_NOT_MODIFIED in str(error).lower()


async def _safe_answer_callback(callback: CallbackQuery, text: str | None = None) -> None:
    try:
        await callback.answer(text)
    except TelegramBadRequest as error:
        logging.info("loading callback answer skipped: %s", error)


async def show_loading(callback: CallbackQuery, *, frames: Sequence[str] | None = None) -> None:
    """Briefly edit the current callback message with loading frames, never failing handlers."""
    user_id = callback.from_user.id if callback.from_user else None
    active_frames = tuple(frames or LOADING_FRAMES)
    logging.info("loading started (%s)", user_id)

    try:
        await _safe_answer_callback(callback)
        message = callback.message
        if message is None:
            logging.info("loading frame skipped (%s): no message", user_id)
            return

        edited_any = False
        for frame in active_frames:
            try:
                await message.edit_text(frame)
                edited_any = True
                logging.info("loading frame updated (%s): text", user_id)
            except TelegramBadRequest as text_error:
                if _is_not_modified(text_error):
                    logging.info("loading frame skipped (%s): not modified", user_id)
                    continue
                try:
                    await message.edit_caption(caption=frame)
                    edited_any = True
                    logging.info("loading frame updated (%s): caption", user_id)
                except TelegramBadRequest as caption_error:
                    if _is_not_modified(caption_error):
                        logging.info("loading frame skipped (%s): not modified", user_id)
                        continue
                    logging.info("loading frame edit failed (%s): %s", user_id, caption_error)
                    if not edited_any:
                        await _safe_answer_callback(callback, _LOADING_FALLBACK_TEXT)
                    break
            await asyncio.sleep(0.12)
    except TelegramBadRequest as error:
        logging.info("loading frame edit failed (%s): %s", user_id, error)
    finally:
        logging.info("loading finished (%s)", user_id)


async def show_message_loading(
    message: Message, *, frames: Sequence[str] | None = None
) -> Message | None:
    """Send a short-lived loading message for non-callback artwork actions."""
    user_id = message.from_user.id if message.from_user else None
    logging.info("loading started (%s)", user_id)
    loading_message: Message | None = None
    try:
        active_frames = tuple(frames or LOADING_FRAMES)
        loading_message = await message.answer(active_frames[0])
        logging.info("loading frame updated (%s): text", user_id)
        for frame in active_frames[1:]:
            try:
                await loading_message.edit_text(frame)
                logging.info("loading frame updated (%s): text", user_id)
            except TelegramBadRequest as error:
                logging.info("loading frame edit failed (%s): %s", user_id, error)
                break
            await asyncio.sleep(0.12)
        return loading_message
    except TelegramBadRequest as error:
        logging.info("loading frame edit failed (%s): %s", user_id, error)
        return loading_message
    finally:
        logging.info("loading finished (%s)", user_id)
