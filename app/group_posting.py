from __future__ import annotations

import asyncio
import html
import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from aiogram import Bot
from aiogram.enums import ParseMode

from app.models import BooruPost
from app.providers.registry import fallback_search

logger = logging.getLogger(__name__)
POST_ERROR = "Не удалось опубликовать. Проверь, что бот добавлен в группу и имеет право писать."
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


def tags_for_mode(mode: str, tags: str | None) -> str:
    base = (tags or "").strip()
    mode = mode.lower()
    if mode == "sfw" and "rating:" not in base:
        return (base + " rating:safe").strip()
    if mode == "nsfw" and "rating:" not in base:
        return (base + " rating:explicit").strip()
    return base


def format_caption(post: BooruPost) -> str:
    return html.escape(
        f"🖼 Источник: {post.provider}\n🆔 ID: {post.post_id}\n⭐ Rating: {post.rating or 'unknown'}"
    )


def split_tag_blocks(tags: list[str], max_len: int = MAX_TAG_BLOCK) -> list[str]:
    escaped = [html.escape(tag) for tag in tags]
    prefix = "<blockquote expandable>\n🏷 Теги:\n"
    suffix = "\n</blockquote>"
    blocks: list[str] = []
    current = ""
    for tag in escaped:
        piece = tag if not current else ", " + tag
        if current and len(prefix) + len(current) + len(piece) + len(suffix) > max_len:
            blocks.append(prefix + current + suffix)
            current = tag
        else:
            current += piece
    if current or not blocks:
        blocks.append(prefix + current + suffix)
    return blocks


async def find_unique_post(db, providers_map, settings: dict[str, Any]) -> BooruPost | None:
    target_chat_id = int(settings["target_chat_id"])
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
        if not await db.group_post_seen(target_chat_id, post.provider, post.post_id):
            return post
    logger.warning("No unique group post found for chat %s after 10 retries", target_chat_id)
    return None


async def publish_group_post(bot: Bot, db, providers_map, settings: dict[str, Any]) -> bool:
    if not settings.get("target_chat_id"):
        logger.warning("Group posting skipped: target chat is not configured")
        return False
    post = await find_unique_post(db, providers_map, settings)
    if not post:
        return False
    target_chat_id = int(settings["target_chat_id"])
    try:
        await bot.send_photo(
            target_chat_id,
            post.file_url,
            caption=format_caption(post),
            parse_mode=ParseMode.HTML,
        )
        for block in split_tag_blocks(post.tags):
            await bot.send_message(target_chat_id, block, parse_mode=ParseMode.HTML)
    except Exception as exc:
        logger.exception("%s: %s", POST_ERROR, exc)
        return False
    await db.add_group_post_history(
        target_chat_id, post.provider, post.post_id, post.file_url, " ".join(post.tags)
    )
    await db.touch_group_posted_at(utcnow_iso())
    return True


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
                    ok = await publish_group_post(bot, db, providers_map, dict(settings))
                    if not ok:
                        await db.touch_group_posted_at(utcnow_iso())
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Group posting scheduler tick failed")
        await asyncio.sleep(60)


def start_scheduler(bot: Bot, db, providers_map) -> asyncio.Task:
    return asyncio.create_task(scheduler_loop(bot, db, providers_map))
