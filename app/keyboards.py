from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def search_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔎 Отправиться на поиски", callback_data="search:start")]
        ]
    )
