from aiogram import Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from app.handlers.search import post_cache, run_search
from app.keyboards import favorite_keyboard, history_keyboard
from app.ui.sessions import callback_sessions, parse_callback
from app.ui.texts import FAVORITES_EMPTY, SESSION_EXPIRED

router = Router()


@router.callback_query(lambda c: c.data and c.data.startswith("fav:"))
async def save_favorite(callback: CallbackQuery, db) -> None:
    parsed = parse_callback(callback.data)
    if not parsed:
        await callback.answer("Кнопка устарела. Открой меню заново.", show_alert=True)
        return
    _, key = parsed
    session = callback_sessions.get(key, callback.from_user.id)
    if not session or not session.current_post_id:
        await callback.answer(SESSION_EXPIRED, show_alert=True)
        return
    post = post_cache.get((callback.from_user.id, session.current_post_id))
    if not post:
        await callback.answer(SESSION_EXPIRED, show_alert=True)
        return
    await db.add_favorite(
        callback.from_user.id, session.provider, post.post_id, post.file_url, post.tags
    )
    await callback.answer("Добавлено в избранное.")


async def show_favorite(target, db, page: int = 0, *, user_id: int | None = None) -> None:
    user_id = user_id or target.from_user.id
    total = await db.count_favorites(user_id)
    if total == 0:
        await target.answer(FAVORITES_EMPTY)
        return
    page = max(0, min(page, total - 1))
    row = (await db.list_favorites(user_id, 1, page))[0]
    caption = f"⭐ Избранное {page + 1}/{total}\nИсточник: {row['provider']}\nID: {row['post_id']}"
    try:
        await target.answer_photo(
            row["file_url"], caption=caption, reply_markup=favorite_keyboard(row["id"], page, total)
        )
    except Exception:
        await target.answer(
            f"{caption}\n{row['file_url']}", reply_markup=favorite_keyboard(row["id"], page, total)
        )


@router.message(Command("favorites"))
async def favorites(message: Message, db) -> None:
    await show_favorite(message, db)


@router.callback_query(lambda c: c.data and c.data.startswith("favorites_page:"))
async def favorites_page(callback: CallbackQuery, db) -> None:
    await show_favorite(
        callback.message, db, int(callback.data.rsplit(":", 1)[1]), user_id=callback.from_user.id
    )
    await callback.answer()


@router.callback_query(lambda c: c.data and c.data.startswith("remove_favorite:"))
async def remove_favorite_callback(callback: CallbackQuery, db) -> None:
    _, raw_id, raw_page = callback.data.split(":", 2)
    await db.remove_favorite(callback.from_user.id, int(raw_id))
    await callback.answer("Удалено.")
    await show_favorite(callback.message, db, int(raw_page), user_id=callback.from_user.id)


@router.message(Command("remove_favorite"))
async def remove_favorite(message: Message, db) -> None:
    raw = message.text.split(maxsplit=1)[1].strip() if len(message.text.split()) > 1 else ""
    if not raw.isdigit():
        await message.answer("Использование: /remove_favorite <id>")
        return
    await db.remove_favorite(message.from_user.id, int(raw))
    await message.answer("Удалено.")


async def show_history(target, db, *, user_id: int | None = None) -> None:
    user_id = user_id or target.from_user.id
    rows = await db.recent_history(user_id, 10)
    queries = [row["query"] for row in rows]
    if not queries:
        await target.answer("История пока пуста.")
        return
    await target.answer("🕘 История", reply_markup=history_keyboard(queries))


@router.message(Command("history"))
async def history(message: Message, db) -> None:
    await show_history(message, db)


@router.callback_query(lambda c: c.data == "history")
async def history_button(callback: CallbackQuery, db) -> None:
    await show_history(callback.message, db, user_id=callback.from_user.id)
    await callback.answer()


@router.callback_query(lambda c: c.data and c.data.startswith("history_repeat:"))
async def history_repeat(callback: CallbackQuery, db, settings, providers_map) -> None:
    idx = int(callback.data.rsplit(":", 1)[1])
    rows = await db.recent_history(callback.from_user.id, 10)
    if idx >= len(rows):
        await callback.answer("Кнопка устарела. Открой меню заново.", show_alert=True)
        return
    await run_search(
        callback.message,
        db,
        settings,
        providers_map,
        rows[idx]["query"],
        user_id=callback.from_user.id,
        username=callback.from_user.username,
    )
    await callback.answer()
