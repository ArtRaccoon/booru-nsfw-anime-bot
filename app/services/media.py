from __future__ import annotations

import logging
from pathlib import PurePosixPath
from urllib.parse import unquote, urlsplit

import httpx
from aiogram import Bot
from aiogram.types import BufferedInputFile, Message

from app.config import Settings, get_settings
from app.models import Post

logger = logging.getLogger(__name__)

PHOTO_MAX_BYTES = 20 * 1024 * 1024
USER_AGENT = "booru-nsfw-anime-bot/1.0"


def post_caption(post: Post) -> str:
    return f"Источник: {post.provider}\nID: {post.post_id}\nRating: {post.rating or 'unknown'}"


def _filename_from_url(url: str, content_type: str | None = None) -> str:
    path = unquote(urlsplit(url).path)
    name = PurePosixPath(path).name or "media"
    if "." not in name:
        if content_type == "image/png":
            name += ".png"
        elif content_type in {"image/gif", "video/gif"}:
            name += ".gif"
        elif content_type == "image/webp":
            name += ".webp"
        else:
            name += ".jpg"
    return name


async def _download_media(url: str, settings: Settings) -> tuple[bytes, str | None]:
    logger.info("Media download started: %s", url)
    async with httpx.AsyncClient(
        proxy=settings.proxy_url,
        timeout=20.0,
        follow_redirects=True,
        headers={"User-Agent": USER_AGENT},
    ) as client:
        response = await client.get(url)
        response.raise_for_status()

    content = response.content
    content_type = response.headers.get("content-type", "").split(";", maxsplit=1)[0].lower()
    logger.info("Media download success: content_type=%s size=%d", content_type, len(content))
    return content, content_type or None


async def _send_direct_url(
    bot: Bot, chat_id: int | str, post: Post, reply_to: Message | None = None
) -> Message:
    logger.info("Direct URL fallback used: %s", post.file_url)
    return await bot.send_photo(
        chat_id,
        post.file_url,
        caption=post_caption(post),
        reply_to_message_id=reply_to.message_id if reply_to else None,
    )


async def send_post(
    bot: Bot,
    chat_id: int | str,
    post: Post,
    reply_to: Message | None = None,
    settings: Settings | None = None,
) -> Message:
    settings = settings or get_settings()
    download_error: Exception | None = None
    caption = post_caption(post)
    reply_to_message_id = reply_to.message_id if reply_to else None

    try:
        content, content_type = await _download_media(post.file_url, settings)
        filename = _filename_from_url(post.file_url, content_type)
        media_file = BufferedInputFile(content, filename=filename)

        if content_type and content_type.startswith("image/") and len(content) <= PHOTO_MAX_BYTES:
            message = await bot.send_photo(
                chat_id,
                media_file,
                caption=caption,
                reply_to_message_id=reply_to_message_id,
            )
        else:
            message = await bot.send_document(
                chat_id,
                media_file,
                caption=caption,
                reply_to_message_id=reply_to_message_id,
            )
        logger.info("Buffered send success: content_type=%s size=%d", content_type, len(content))
        return message
    except Exception as exc:  # noqa: BLE001
        download_error = exc

    try:
        return await _send_direct_url(bot, chat_id, post, reply_to)
    except Exception as fallback_exc:  # noqa: BLE001
        logger.exception(
            "Both buffered media delivery and direct URL fallback failed: "
            "download_error=%r fallback_error=%r",
            download_error,
            fallback_exc,
        )
        text = (
            "Telegram не смог загрузить изображение по URL.\n"
            f"Источник: {post.provider}\nID: {post.post_id}\n"
            f"Ошибка загрузки через бота: {download_error}\n"
            f"Ошибка прямой отправки URL: {fallback_exc}"
        )
        return await bot.send_message(chat_id, text)
