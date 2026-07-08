from __future__ import annotations

from aiogram import F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InputMediaPhoto, Message

from app.bot import AppContext, get_context
from app.keyboards import main_menu, post_nav
from app.models import Post
from app.services.media import post_caption, send_post

router = Router()


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


async def save_shown_post(
    ctx: AppContext, user_id: int, post: Post, *, tags: str = "", mode: str = "random"
) -> None:
    await ctx.db.execute(
        """
        INSERT INTO post_history(
            user_id, provider, post_id, file_url, preview_url, tags, rating, source_url
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
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
        ),
    )
    row = await ctx.db.fetchone(
        """
        SELECT id FROM post_history
        WHERE user_id = ? AND provider = ? AND post_id = ?
        ORDER BY id DESC LIMIT 1
        """,
        (user_id, post.provider, post.post_id),
    )
    history_id = row["id"] if row else None
    await ctx.db.execute(
        """
        INSERT INTO user_sessions(user_id, provider, tags, mode, current_history_id)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(user_id) DO UPDATE SET
            provider = excluded.provider,
            tags = excluded.tags,
            mode = excluded.mode,
            current_history_id = excluded.current_history_id,
            updated_at = CURRENT_TIMESTAMP
        """,
        (user_id, post.provider, tags, mode, history_id),
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
    current_id = session["current_history_id"] if session else None
    if not current_id:
        return None
    row = await ctx.db.fetchone(
        """
        SELECT * FROM post_history
        WHERE user_id = ? AND id < ?
        ORDER BY id DESC LIMIT 1
        """,
        (user_id, current_id),
    )
    if not row:
        return None
    await ctx.db.execute(
        """
        UPDATE user_sessions
        SET current_history_id = ?, updated_at = CURRENT_TIMESTAMP
        WHERE user_id = ?
        """,
        (row["id"], user_id),
    )
    return _row_to_post(row)


async def fetch_next_post(ctx: AppContext, user_id: int) -> Post | None:
    session = await current_session(ctx, user_id)
    provider = session["provider"] if session else None
    tags = session["tags"] if session else ""
    mode = session["mode"] if session else "random"
    selected = provider or None
    if mode == "search":
        provider_name, posts = await ctx.providers.search(tags or "", selected, 1, 30, False)
        post = posts[0] if posts else None
        if post and not post.provider:
            post.provider = provider_name
    else:
        post = await ctx.providers.random(tags or "", selected, False)
    if post:
        await save_shown_post(ctx, user_id, post, tags=tags or "", mode=mode or "random")
    return post


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
    except TelegramAPIError:
        pass
    sent = await send_post(bot, message.chat.id, post)
    await sent.edit_reply_markup(reply_markup=post_nav())
    return sent


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
    await show_post(message, post)


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
        await show_post(call, post)
    await call.answer()


@router.callback_query(F.data == "post:prev")
async def post_prev(call: CallbackQuery, ctx: AppContext | None = None) -> None:
    post = await previous_post(ctx or get_context(), call.from_user.id)
    if not post:
        await call.answer("Предыдущих постов нет", show_alert=True)
        return
    await show_post(call, post)
    await call.answer()


@router.callback_query(F.data.in_({"post:next", "post:more"}))
async def post_next_more(call: CallbackQuery, ctx: AppContext | None = None) -> None:
    post = await fetch_next_post(ctx or get_context(), call.from_user.id)
    if not post:
        await call.answer("Не удалось найти ещё арт", show_alert=True)
        return
    await show_post(call, post)
    await call.answer()


@router.callback_query(F.data == "post:fav")
async def post_fav(call: CallbackQuery, ctx: AppContext | None = None) -> None:
    added = await add_favorite(ctx or get_context(), call.from_user.id)
    await call.answer("Добавлено в избранное" if added else "Уже в избранном")


@router.callback_query(F.data == "menu:home")
async def post_home(call: CallbackQuery) -> None:
    await call.message.edit_text("Главное меню", reply_markup=main_menu())
    await call.answer()
