from __future__ import annotations

import logging
from io import BytesIO
from pathlib import PurePosixPath
from urllib.parse import unquote, urlsplit

import httpx
from aiogram import Bot
from aiogram.types import BufferedInputFile, Message
from PIL import Image, ImageOps, UnidentifiedImageError

from app.config import Settings, get_settings
from app.models import Post

logger = logging.getLogger(__name__)

PHOTO_MAX_BYTES = 20 * 1024 * 1024
PHOTO_MAX_SIDE = 4096
PHOTO_MAX_DIMENSIONS_SUM = 10000
PHOTO_MAX_ASPECT_RATIO = 20
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


def _jpeg_filename(filename: str) -> str:
    stem = PurePosixPath(filename).stem or "image"
    return f"{stem}.jpg"


def _rgb_image(image: Image.Image) -> Image.Image:
    if image.mode in {"RGBA", "LA", "P"} or (image.mode == "P" and "transparency" in image.info):
        rgba = image.convert("RGBA")
        background = Image.new("RGBA", rgba.size, (255, 255, 255, 255))
        background.alpha_composite(rgba)
        return background.convert("RGB")
    if image.mode != "RGB":
        return image.convert("RGB")
    return image


def _telegram_safe_size(width: int, height: int) -> tuple[int, int] | None:
    if width < 1 or height < 1:
        return None
    aspect_ratio = max(width / height, height / width)
    if aspect_ratio > PHOTO_MAX_ASPECT_RATIO:
        return None

    scale = min(PHOTO_MAX_SIDE / width, PHOTO_MAX_SIDE / height, 1.0)
    if (width * scale) + (height * scale) > PHOTO_MAX_DIMENSIONS_SUM:
        scale = PHOTO_MAX_DIMENSIONS_SUM / (width + height)

    safe_width = max(1, int(width * scale))
    safe_height = max(1, int(height * scale))
    return safe_width, safe_height


def _normalize_photo(
    content: bytes, content_type: str | None
) -> tuple[bytes, tuple[int, int]] | None:
    try:
        with Image.open(BytesIO(content)) as image:
            logger.info(
                "Original image: size=%s mode=%s content_type=%s",
                image.size,
                image.mode,
                content_type,
            )
            image = ImageOps.exif_transpose(image)
            image = _rgb_image(image)
            safe_size = _telegram_safe_size(*image.size)
            if safe_size is None:
                logger.warning("Image cannot be normalized as Telegram photo: size=%s", image.size)
                return None
            if safe_size != image.size:
                image = image.resize(safe_size, Image.Resampling.LANCZOS)
            output = BytesIO()
            image.save(output, format="JPEG", quality=90, optimize=True)
            logger.info("Normalized image: size=%s", image.size)
            return output.getvalue(), image.size
    except (UnidentifiedImageError, OSError) as exc:
        logger.warning("Pillow could not decode image for photo normalization: %r", exc)
        return None


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

        if content_type and content_type.startswith("image/"):
            normalized = _normalize_photo(content, content_type)
            if normalized is not None:
                normalized_content, _ = normalized
                normalized_file = BufferedInputFile(
                    normalized_content, filename=_jpeg_filename(filename)
                )
                try:
                    message = await bot.send_photo(
                        chat_id,
                        normalized_file,
                        caption=caption,
                        reply_to_message_id=reply_to_message_id,
                    )
                    logger.info(
                        "Buffered photo send success: content_type=%s size=%d normalized_size=%d",
                        content_type,
                        len(content),
                        len(normalized_content),
                    )
                    return message
                except Exception as photo_exc:  # noqa: BLE001
                    logger.warning(
                        "Buffered photo failed; document fallback used: error=%r", photo_exc
                    )
                    document_file = BufferedInputFile(
                        normalized_content, filename=_jpeg_filename(filename)
                    )
                    return await bot.send_document(
                        chat_id,
                        document_file,
                        caption=caption,
                        reply_to_message_id=reply_to_message_id,
                    )

        media_file = BufferedInputFile(content, filename=filename)
        message = await bot.send_document(
            chat_id,
            media_file,
            caption=caption,
            reply_to_message_id=reply_to_message_id,
        )
        logger.info(
            "Buffered document send success: content_type=%s size=%d", content_type, len(content)
        )
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
