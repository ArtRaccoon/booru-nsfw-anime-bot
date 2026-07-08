from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import CallbackQuery, Message

from app.config import get_settings
from app.keyboards import main_menu

router = Router()


@router.message(CommandStart())
async def start(message: Message) -> None:
    await message.answer(
        "Главное меню",
        reply_markup=main_menu(
            get_settings().is_admin(message.from_user.id if message.from_user else None)
        ),
    )


@router.callback_query(lambda c: c.data == "menu")
async def menu(call: CallbackQuery) -> None:
    await call.message.edit_text(
        "Главное меню", reply_markup=main_menu(get_settings().is_admin(call.from_user.id))
    )
    await call.answer()
