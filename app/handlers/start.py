from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import CallbackQuery, Message

from app.keyboards import age_gate_keyboard, main_menu_keyboard
from app.safety import is_admin
from app.ui.texts import AGE_GATE, MAIN_MENU

router = Router()


async def show_main_menu(target, settings) -> None:
    await target.answer(
        MAIN_MENU,
        reply_markup=main_menu_keyboard(is_admin=is_admin(target.from_user.id, settings.admin_ids)),
    )


@router.message(CommandStart())
async def start(message: Message, db, settings) -> None:
    await db.upsert_user(message.from_user.id, message.from_user.username)
    if await db.is_confirmed(message.from_user.id):
        await show_main_menu(message, settings)
        return
    await message.answer(AGE_GATE, reply_markup=age_gate_keyboard())


@router.callback_query(lambda c: c.data == "age:confirm")
async def confirm_age(callback: CallbackQuery, db, settings) -> None:
    await db.upsert_user(callback.from_user.id, callback.from_user.username)
    await db.confirm_adult(callback.from_user.id)
    await callback.message.edit_text(
        MAIN_MENU,
        reply_markup=main_menu_keyboard(
            is_admin=is_admin(callback.from_user.id, settings.admin_ids)
        ),
    )
    await callback.answer()


@router.callback_query(lambda c: c.data == "age:exit")
async def exit_age(callback: CallbackQuery) -> None:
    await callback.message.edit_text("Ок. Возвращайся, когда будет 18+.")
    await callback.answer()


@router.callback_query(lambda c: c.data == "main_menu")
async def main_menu(callback: CallbackQuery, settings) -> None:
    await callback.message.edit_text(
        MAIN_MENU,
        reply_markup=main_menu_keyboard(
            is_admin=is_admin(callback.from_user.id, settings.admin_ids)
        ),
    )
    await callback.answer()
