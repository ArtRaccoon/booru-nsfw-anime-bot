from __future__ import annotations

from aiogram import Bot
from aiogram.types import Message

from app.models import Post


def post_caption(post: Post) -> str:
    return f"Источник: {post.provider}\nID: {post.post_id}\nRating: {post.rating or 'unknown'}"


async def send_post(
    bot: Bot, chat_id: int | str, post: Post, reply_to: Message | None = None
) -> Message:
    try:
        return await bot.send_photo(
            chat_id,
            post.file_url,
            caption=post_caption(post),
            reply_to_message_id=reply_to.message_id if reply_to else None,
        )
    except Exception as exc:  # noqa: BLE001
        text = (
            "Telegram не смог загрузить изображение по URL.\n"
            f"Источник: {post.provider}\nID: {post.post_id}\nОшибка: {exc}"
        )
        return await bot.send_message(chat_id, text)
