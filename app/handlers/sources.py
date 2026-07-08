from aiogram import Router
from aiogram.types import CallbackQuery

from app.bot import AppContext, get_context
from app.keyboards import sources_menu

router = Router()


@router.callback_query(lambda c: c.data == "sources")
async def sources(call: CallbackQuery, ctx: AppContext | None = None) -> None:
    ctx = ctx or get_context()
    await call.message.edit_text(
        "Выберите источник", reply_markup=sources_menu(list(ctx.providers.providers))
    )
    await call.answer()


@router.callback_query(lambda c: c.data and c.data.startswith("source:"))
async def select_source(call: CallbackQuery, ctx: AppContext | None = None) -> None:
    name = call.data.split(":", 1)[1]
    auto = int(name == "auto")
    selected = None if auto else name
    ctx = ctx or get_context()
    await ctx.db.execute(
        "INSERT OR REPLACE INTO users(user_id, selected_provider, auto_mode) VALUES (?, ?, ?)",
        (call.from_user.id, selected, auto),
    )
    await call.answer("Источник сохранен")
