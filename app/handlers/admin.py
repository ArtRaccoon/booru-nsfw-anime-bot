from aiogram import Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from app.bot import get_context
from app.config import get_settings
from app.keyboards import admin_menu

router = Router()


def admin_only(user_id: int | None) -> bool:
    return get_settings().is_admin(user_id)


async def providers_report() -> str:
    statuses = await get_context().providers.healthcheck_all()
    lines = ["Проверка источников:"]
    for s in statuses:
        state = "работает" if s.ok else "недоступен"
        lines.append(f"{s.name}: {state}, {s.response_ms} ms, {s.message}")
    return "\n".join(lines)


@router.callback_query(lambda c: c.data == "admin")
async def admin(call: CallbackQuery) -> None:
    if not admin_only(call.from_user.id):
        await call.answer("Недоступно", show_alert=True)
        return
    await call.message.edit_text("Админка", reply_markup=admin_menu())
    await call.answer()


@router.message(Command("providers_check"))
async def providers_check_cmd(message: Message) -> None:
    if not admin_only(message.from_user.id if message.from_user else None):
        return
    await message.answer(await providers_report())


@router.callback_query(lambda c: c.data == "providers_check")
async def providers_check_btn(call: CallbackQuery) -> None:
    if not admin_only(call.from_user.id):
        await call.answer("Недоступно", show_alert=True)
        return
    await call.message.edit_text(await providers_report(), reply_markup=admin_menu())
    await call.answer()
