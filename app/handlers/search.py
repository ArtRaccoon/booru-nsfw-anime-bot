from __future__ import annotations

import logging
from contextlib import suppress

from aiogram import F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InputMediaPhoto, Message

from app.bot import AppContext, get_context
from app.keyboards import main_menu, post_nav
from app.models import Post
from app.services.media import post_caption, send_post

router = Router()
logger = logging.getLogger(__name__)
MAX_UNIQUE_ATTEMPTS = 10


def _row_to_post(row) -> Post:
    return Post(
        provider=row["provider"],
        post_id=row["post_id"],
        file_url=row["file_url"],
        preview_url=row["preview_url"],
        page_url=row["source_url"],
        rating=row["rating"],
        tags=row["tags"] or "",
    )


def _session_provider(session) -> str | None:
    if not session:
        return None
    return session["current_provider"] or session["provider"]


def _session_tags(session) -> str:
    if not session:
        return ""
    return session["current_tags"] or session["tags"] or ""


def _session_mode(session) -> str:
    if not session:
        return "random"
    return session["current_mode"] or session["mode"] or "random"


async def _context_history(
    ctx: AppContext, user_id: int, provider: str | None, tags: str, mode: str
):
    return await ctx.db.fetchall(
        """
        SELECT * FROM post_history
        WHERE user_id = ? AND provider = COALESCE(?, provider) AND context_tags = ? AND mode = ?
        ORDER BY history_index ASC, id ASC
        """,
        (user_id, provider, tags, mode),
    )


async def save_shown_post(
    ctx: AppContext, user_id: int, post: Post, *, tags: str = "", mode: str = "random"
) -> bool:
    existing = await ctx.db.fetchone(
        """
        SELECT * FROM post_history
        WHERE user_id = ? AND provider = ? AND post_id = ? AND context_tags = ? AND mode = ?
        """,
        (user_id, post.provider, post.post_id, tags, mode),
    )
    if existing:
        logger.info(
            "Duplicate skipped: user_id=%s provider=%s post_id=%s mode=%s tags=%r",
            user_id,
            post.provider,
            post.post_id,
            mode,
            tags,
        )
        await _update_session(
            ctx, user_id, existing["id"], existing["history_index"], post.provider, tags, mode
        )
        return False

    row = await ctx.db.fetchone(
        """
        SELECT COALESCE(MAX(history_index), -1) + 1 AS next_index
        FROM post_history WHERE user_id = ? AND provider = ? AND context_tags = ? AND mode = ?
        """,
        (user_id, post.provider, tags, mode),
    )
    history_index = int(row["next_index"] if row else 0)
    await ctx.db.execute(
        """
        INSERT INTO post_history(
            user_id, provider, post_id, file_url, preview_url, tags, rating, source_url,
            mode, context_tags, history_index
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            user_id,
            post.provider,
            post.post_id,
            post.file_url,
            post.preview_url,
            post.tags or tags,
            post.rating,
            post.page_url,
            mode,
            tags,
            history_index,
        ),
    )
    inserted = await ctx.db.fetchone(
        """
        SELECT id FROM post_history
        WHERE user_id = ? AND provider = ? AND post_id = ? AND context_tags = ? AND mode = ?
        """,
        (user_id, post.provider, post.post_id, tags, mode),
    )
    await _update_session(ctx, user_id, inserted["id"], history_index, post.provider, tags, mode)
    return True


async def _update_session(
    ctx,
    user_id,
    history_id,
    history_index,
    provider,
    tags,
    mode,
    page: int | None = None,
    message_id: int | None = None,
):
    old = await current_session(ctx, user_id)
    current_page = page if page is not None else (old["current_page"] if old else 1)
    current_message_id = (
        message_id if message_id is not None else (old["current_message_id"] if old else None)
    )
    await ctx.db.execute(
        """
        INSERT INTO user_sessions(
            user_id, provider, current_provider, tags, current_tags, mode, current_mode,
            current_page, current_history_id, current_history_index, current_message_id
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(user_id) DO UPDATE SET
            provider = excluded.provider, current_provider = excluded.current_provider,
            tags = excluded.tags, current_tags = excluded.current_tags,
            mode = excluded.mode, current_mode = excluded.current_mode,
            current_page = excluded.current_page,
            current_history_id = excluded.current_history_id,
            current_history_index = excluded.current_history_index,
            current_message_id = COALESCE(
                excluded.current_message_id, user_sessions.current_message_id
            ),
            updated_at = CURRENT_TIMESTAMP
        """,
        (
            user_id,
            provider,
            provider,
            tags,
            tags,
            mode,
            mode,
            current_page,
            history_id,
            history_index,
            current_message_id,
        ),
    )


async def current_session(ctx: AppContext, user_id: int):
    return await ctx.db.fetchone("SELECT * FROM user_sessions WHERE user_id = ?", (user_id,))


async def current_post(ctx: AppContext, user_id: int) -> Post | None:
    row = await ctx.db.fetchone(
        """
        SELECT h.* FROM post_history h
        JOIN user_sessions s ON s.current_history_id = h.id
        WHERE s.user_id = ?
        """,
        (user_id,),
    )
    return _row_to_post(row) if row else None


async def add_favorite(ctx: AppContext, user_id: int) -> bool:
    post = await current_post(ctx, user_id)
    if not post:
        return False
    before = await ctx.db.fetchone(
        "SELECT 1 FROM favorites WHERE user_id = ? AND provider = ? AND post_id = ?",
        (user_id, post.provider, post.post_id),
    )
    if before:
        return False
    await ctx.db.execute(
        """
        INSERT OR IGNORE INTO favorites(
            user_id, provider, post_id, file_url, page_url, rating, tags
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            user_id,
            post.provider,
            post.post_id,
            post.file_url,
            post.page_url,
            post.rating,
            post.tags,
        ),
    )
    return True


async def previous_post(ctx: AppContext, user_id: int) -> Post | None:
    session = await current_session(ctx, user_id)
    if not session or session["current_history_index"] <= 0:
        return None
    index = session["current_history_index"] - 1
    row = await ctx.db.fetchone(
        """
        SELECT * FROM post_history
        WHERE user_id = ? AND provider = ? AND context_tags = ? AND mode = ? AND history_index = ?
        """,
        (
            user_id,
            _session_provider(session),
            _session_tags(session),
            _session_mode(session),
            index,
        ),
    )
    if not row:
        return None
    await _update_session(
        ctx,
        user_id,
        row["id"],
        row["history_index"],
        row["provider"],
        row["context_tags"],
        row["mode"],
    )
    logger.info("Navigation action=prev user_id=%s index=%s", user_id, index)
    return _row_to_post(row)


async def next_post(ctx: AppContext, user_id: int) -> Post | None:
    session = await current_session(ctx, user_id)
    if session:
        index = session["current_history_index"] + 1
        row = await ctx.db.fetchone(
            """
            SELECT * FROM post_history
            WHERE user_id = ? AND provider = ? AND context_tags = ?
                AND mode = ? AND history_index = ?
            """,
            (
                user_id,
                _session_provider(session),
                _session_tags(session),
                _session_mode(session),
                index,
            ),
        )
        if row:
            await _update_session(
                ctx,
                user_id,
                row["id"],
                row["history_index"],
                row["provider"],
                row["context_tags"],
                row["mode"],
            )
            logger.info("Navigation action=next_existing user_id=%s index=%s", user_id, index)
            return _row_to_post(row)
    return await fetch_next_post(ctx, user_id, action="next")


async def fetch_next_post(ctx: AppContext, user_id: int, *, action: str = "more") -> Post | None:
    session = await current_session(ctx, user_id)
    provider = _session_provider(session)
    tags = _session_tags(session)
    mode = _session_mode(session)
    page = int(session["current_page"] if session else 1)
    history = await _context_history(ctx, user_id, provider, tags, mode)
    shown = {(r["provider"], r["post_id"]) for r in history}
    logger.info(
        "Navigation action=%s user_id=%s index=%s history_len=%s",
        action,
        user_id,
        session["current_history_index"] if session else 0,
        len(history),
    )

    for attempt in range(MAX_UNIQUE_ATTEMPTS):
        if mode == "search":
            provider_name, posts = await ctx.providers.search(tags or "", provider, page, 30, False)
            candidates = posts or []
        else:
            provider_name = provider
            candidates = [await ctx.providers.random(tags or "", provider, False)]
        for post in filter(None, candidates):
            if not post.provider:
                post.provider = provider_name or provider or "unknown"
            logger.info(
                "Fetched provider=%s post_id=%s attempt=%s page=%s",
                post.provider,
                post.post_id,
                attempt + 1,
                page,
            )
            if (post.provider, post.post_id) in shown:
                logger.info(
                    "Duplicate skipped: provider=%s post_id=%s", post.provider, post.post_id
                )
                continue
            await save_shown_post(ctx, user_id, post, tags=tags, mode=mode)
            if mode == "search":
                await _update_session(
                    ctx,
                    user_id,
                    (await current_session(ctx, user_id))["current_history_id"],
                    (await current_session(ctx, user_id))["current_history_index"],
                    post.provider,
                    tags,
                    mode,
                    page=page,
                )
            return post
        if mode == "search":
            page += 1
        else:
            page += 1
            if session:
                await _update_session(
                    ctx,
                    user_id,
                    session["current_history_id"],
                    session["current_history_index"],
                    provider,
                    tags,
                    mode,
                    page=page,
                )
    return None


async def show_post(target: Message | CallbackQuery, post: Post) -> Message | None:
    message = target.message if isinstance(target, CallbackQuery) else target
    bot = target.bot if isinstance(target, CallbackQuery) else target.bot
    try:
        if isinstance(target, CallbackQuery):
            await message.edit_media(
                media=InputMediaPhoto(media=post.file_url, caption=post_caption(post)),
                reply_markup=post_nav(),
            )
            return message
    except TelegramAPIError as exc:
        logger.info("Edit failed fallback used: %r", exc)
        try:
            await message.delete()
        except TelegramAPIError as delete_exc:
            logger.info("Delete old message failed: %r", delete_exc)
    sent = await send_post(bot, message.chat.id, post)
    await sent.edit_reply_markup(reply_markup=post_nav())
    return sent


async def _show_and_track(call: CallbackQuery, ctx: AppContext, post: Post) -> None:
    sent = await show_post(call, post)
    if sent and getattr(sent, "message_id", None):
        session = await current_session(ctx, call.from_user.id)
        if session:
            await _update_session(
                ctx,
                call.from_user.id,
                session["current_history_id"],
                session["current_history_index"],
                _session_provider(session),
                _session_tags(session),
                _session_mode(session),
                message_id=sent.message_id,
            )


@router.message(Command("search"))
async def search_cmd(message: Message, ctx: AppContext | None = None) -> None:
    tags = message.text.partition(" ")[2].strip()
    if not tags:
        await message.answer("Введите теги после /search")
        return
    ctx = ctx or get_context()
    provider, posts = await ctx.providers.search(tags)
    if not posts:
        await message.answer("Ничего не найдено.")
        return
    post = posts[0]
    await ctx.db.execute(
        "INSERT INTO search_history(user_id, provider, tags, post_id) VALUES (?, ?, ?, ?)",
        (message.from_user.id, provider, tags, post.post_id),
    )
    await save_shown_post(ctx, message.from_user.id, post, tags=tags, mode="search")
    sent = await show_post(message, post)
    if sent and getattr(sent, "message_id", None):
        session = await current_session(ctx, message.from_user.id)
        await _update_session(
            ctx,
            message.from_user.id,
            session["current_history_id"],
            session["current_history_index"],
            provider,
            tags,
            "search",
            message_id=sent.message_id,
        )


@router.callback_query(F.data == "search")
async def search_prompt(call: CallbackQuery) -> None:
    await call.message.edit_text("Отправьте /search теги для поиска.")
    await call.answer()


@router.callback_query(F.data == "random")
async def random_art(call: CallbackQuery, ctx: AppContext | None = None) -> None:
    ctx = ctx or get_context()
    post = await ctx.providers.random()
    if not post:
        await call.message.edit_text("Не удалось найти случайный арт.")
    else:
        await save_shown_post(ctx, call.from_user.id, post, mode="random")
        await _show_and_track(call, ctx, post)
    await call.answer()


@router.callback_query(F.data == "post:prev")
async def post_prev(call: CallbackQuery, ctx: AppContext | None = None) -> None:
    ctx = ctx or get_context()
    post = await previous_post(ctx, call.from_user.id)
    if not post:
        await call.answer("Это первый пост", show_alert=True)
        return
    await _show_and_track(call, ctx, post)
    await call.answer()


@router.callback_query(F.data == "post:next")
async def post_next(call: CallbackQuery, ctx: AppContext | None = None) -> None:
    ctx = ctx or get_context()
    post = await next_post(ctx, call.from_user.id)
    if not post:
        await call.answer("Не нашла новый арт, попробуй ещё раз", show_alert=True)
        return
    await _show_and_track(call, ctx, post)
    await call.answer()


@router.callback_query(F.data == "post:more")
async def post_more(call: CallbackQuery, ctx: AppContext | None = None) -> None:
    ctx = ctx or get_context()
    post = await fetch_next_post(ctx, call.from_user.id, action="more")
    if not post:
        await call.answer("Не нашла новый арт, попробуй ещё раз", show_alert=True)
        return
    await _show_and_track(call, ctx, post)
    await call.answer()


@router.callback_query(F.data == "post:fav")
async def post_fav(call: CallbackQuery, ctx: AppContext | None = None) -> None:
    added = await add_favorite(ctx or get_context(), call.from_user.id)
    await call.answer("Добавлено в избранное" if added else "Уже в избранном")


@router.callback_query(F.data == "menu:home")
async def post_home(call: CallbackQuery) -> None:
    try:
        await call.message.edit_text("Главное меню", reply_markup=main_menu())
    except TelegramAPIError as exc:
        logger.info("Home edit failed fallback used: %r", exc)
        with suppress(TelegramAPIError):
            await call.message.delete()
        await call.message.answer("Главное меню", reply_markup=main_menu())
    await call.answer()
