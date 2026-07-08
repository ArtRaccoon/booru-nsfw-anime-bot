from aiogram import Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from app.bot import AppContext, get_context

router = Router()


@router.message(Command("favorites"))
async def favorites(message: Message, ctx: AppContext | None = None) -> None:
    ctx = ctx or get_context()
    rows = await ctx.db.fetchall(
        "SELECT * FROM favorites WHERE user_id = ? ORDER BY id DESC LIMIT 10",
        (message.from_user.id,),
    )
    text = (
        "Избранное пусто."
        if not rows
        else "\n".join(f"{r['id']}. {r['provider']} #{r['post_id']}" for r in rows)
    )
    await message.answer(text)


@router.callback_query(lambda c: c.data == "favorites")
async def favorites_button(call: CallbackQuery, ctx: AppContext | None = None) -> None:
    ctx = ctx or get_context()
    rows = await ctx.db.fetchall(
        "SELECT * FROM favorites WHERE user_id = ? ORDER BY id DESC LIMIT 10", (call.from_user.id,)
    )
    text = (
        "Избранное пусто."
        if not rows
        else "\n".join(f"{r['id']}. {r['provider']} #{r['post_id']}" for r in rows)
    )
    await call.message.edit_text(text)
    await call.answer()
