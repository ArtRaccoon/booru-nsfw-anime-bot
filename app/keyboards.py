from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def search_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔎 Отправиться на поиски", callback_data="search:start")]
        ]
    )


def main_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🎲 Рандомный арт", callback_data="menu:random")],
            [InlineKeyboardButton(text="⭐ Избранное", callback_data="menu:favorites")],
            [InlineKeyboardButton(text="🔎 Поиск", callback_data="menu:search")],
            [InlineKeyboardButton(text="💎 Премиум", callback_data="menu:premium")],
        ]
    )
