from aiogram import Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from app.handlers.search import post_cache

router = Router()


@router.callback_query(lambda c: c.data.startswith("fav:"))
async def save_favorite(callback: CallbackQuery, db) -> None:
    _, provider, post_id = callback.data.split(":", 2)
    post = post_cache.get((callback.from_user.id, post_id))
    if not post:
        await callback.answer("Post cache expired.", show_alert=True)
        return
    await db.add_favorite(callback.from_user.id, provider, post.post_id, post.file_url, post.tags)
    await callback.answer("Saved.")


@router.message(Command("favorites"))
async def favorites(message: Message) -> None:
    await message.answer(
        "Favorites are saved. Full listing UI will be expanded in a future version."
    )


@router.message(Command("history"))
async def history(message: Message) -> None:
    await message.answer(
        "Search history is being recorded. Full listing UI will be expanded in a future version."
    )
