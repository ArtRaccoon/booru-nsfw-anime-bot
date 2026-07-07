from __future__ import annotations

import asyncio
import html
import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from aiogram import Bot
from aiogram.enums import ParseMode
from aiogram.types import Message

from app.models import BooruPost
from app.providers.registry import fallback_search

logger = logging.getLogger(__name__)
POST_ERROR = "Не удалось опубликовать. Проверь, что бот добавлен в канал и имеет право писать."
POSITIVE_ID_WARNING = "Похоже, это не полный ID канала. Для каналов обычно нужен формат -100..."
MAX_TAG_BLOCK = 3500


def utcnow_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def resolve_channel_target(input_or_forwarded_message: str | Message | None) -> int | str:
    if isinstance(input_or_forwarded_message, Message):
        sender_chat = getattr(input_or_forwarded_message, "sender_chat", None)
        if sender_chat and getattr(sender_chat, "id", None):
            return int(sender_chat.id)
        text = (input_or_forwarded_message.text or "").strip()
    else:
        text = (input_or_forwarded_message or "").strip()
    if not text:
        raise ValueError("empty channel target")
    if text.startswith("@"):
        return text
    try:
        return int(text)
    except ValueError as exc:
        raise ValueError("channel target must be -100 id or @username") from exc


def positive_id_warning(target: int | str) -> str | None:
    if isinstance(target, int) and target > 0:
        return POSITIVE_ID_WARNING
    return None


def target_to_db(target: int | str) -> int | str:
    return target


def tags_for_mode(mode: str, tags: str | None) -> str:
    base = (tags or "").strip()
    mode = mode.lower()
    if mode == "sfw" and "rating:" not in base:
        return (base + " rating:safe").strip()
    if mode == "nsfw" and "rating:" not in base:
        return (base + " rating:explicit").strip()
    return base


def format_caption(post: BooruPost) -> str:
    provider = html.escape(post.provider.title())
    post_id = html.escape(str(post.post_id))
    rating = html.escape(post.rating or "unknown")
    return f"🖼 Источник: {provider}\n🆔 ID: {post_id}\n⭐ Rating: {rating}"


def _tag_block(body: str, expandable: bool = True) -> str:
    kind = "blockquote expandable" if expandable else "blockquote"
    return f"<{kind}>\n🏷 Теги:\n{body}\n</blockquote>"


def split_tag_blocks(
    tags: list[str], max_len: int = MAX_TAG_BLOCK, *, expandable: bool = True
) -> list[str]:
    escaped = [html.escape(tag) for tag in tags]
    blocks: list[str] = []
    current = ""
    for tag in escaped:
        piece = tag if not current else ", " + tag
        if current and len(_tag_block(current + piece, expandable)) > max_len:
            blocks.append(_tag_block(current, expandable))
            current = tag
        else:
            current += piece
    if current or not blocks:
        blocks.append(_tag_block(current, expandable))
    return blocks


async def find_unique_post(db, providers_map, settings: dict[str, Any]) -> BooruPost | None:
    target = settings["target_chat_id"]
    configured_provider = (settings.get("provider") or "auto").strip()
    providers = providers_map
    if (
        configured_provider
        and configured_provider != "auto"
        and configured_provider in providers_map
    ):
        providers = {configured_provider: providers_map[configured_provider]}
    query = tags_for_mode(settings.get("mode", "sfw"), settings.get("tags"))
    for _ in range(10):
        provider, posts = await fallback_search(providers, query, 1, 1)
        if not provider or not posts:
            continue
        post = posts[0]
        if not await db.group_post_seen(target, post.provider, post.post_id):
            return post
    logger.warning("No unique channel post found for target %s after 10 retries", target)
    return None


async def _send_tag_blocks(bot: Bot, target: int | str, tags: list[str]) -> None:
    try:
        for block in split_tag_blocks(tags, expandable=True):
            await bot.send_message(target, block, parse_mode=ParseMode.HTML)
    except Exception as exc:
        if "expandable" not in str(exc).lower():
            raise
        for block in split_tag_blocks(tags, expandable=False):
            await bot.send_message(target, block, parse_mode=ParseMode.HTML)


async def publish_channel_post(
    bot: Bot, db, providers_map, settings: dict[str, Any]
) -> tuple[bool, str | None]:
    if not settings.get("target_chat_id"):
        logger.warning("Channel posting skipped: target channel is not configured")
        return False, "Канал не задан."
    post = await find_unique_post(db, providers_map, settings)
    if not post:
        return False, "Не удалось найти уникальный пост после 10 попыток."
    target = settings["target_chat_id"]
    try:
        await bot.send_photo(
            target, post.file_url, caption=format_caption(post), parse_mode=ParseMode.HTML
        )
        await _send_tag_blocks(bot, target, post.tags)
    except Exception as exc:
        logger.exception("%s: %s", POST_ERROR, exc)
        return False, f"Ошибка: {type(exc).__name__}\nОписание: {exc}"
    await db.add_group_post_history(
        target, post.provider, post.post_id, post.file_url, " ".join(post.tags)
    )
    await db.touch_group_posted_at(utcnow_iso())
    return True, None


async def test_channel(bot: Bot, target: int | str) -> tuple[bool, str]:
    try:
        await bot.get_chat(target)
        msg = await bot.send_message(target, "🧪", disable_notification=True)
        try:
            await bot.delete_message(target, msg.message_id)
        except Exception as exc:
            text = (
                "Доступ есть, тестовое сообщение отправлено. "
                f"Не удалось удалить: {type(exc).__name__}: {exc}"
            )
            return True, text
        return True, "Доступ есть, бот может публиковать в канал."
    except Exception as exc:
        return False, f"Ошибка: {type(exc).__name__}\nОписание: {exc}\nКанал: {target}"


async def scheduler_loop(bot: Bot, db, providers_map) -> None:
    while True:
        try:
            settings = await db.get_group_posting_settings()
            if settings and settings["enabled"] and settings["target_chat_id"]:
                last = parse_dt(settings["last_posted_at"])
                due = last is None or datetime.now(UTC) >= last + timedelta(
                    minutes=int(settings["interval_minutes"])
                )
                if due:
                    ok, _ = await publish_channel_post(bot, db, providers_map, dict(settings))
                    if not ok:
                        await db.touch_group_posted_at(utcnow_iso())
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Channel posting scheduler tick failed")
        await asyncio.sleep(60)


def start_scheduler(bot: Bot, db, providers_map) -> asyncio.Task:
    return asyncio.create_task(scheduler_loop(bot, db, providers_map))
