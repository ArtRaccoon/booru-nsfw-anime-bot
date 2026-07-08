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


def random_art_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="⬅️ Назад", callback_data="random:previous"),
                InlineKeyboardButton(text="⭐ Сохранить", callback_data="random:save"),
                InlineKeyboardButton(text="➡️ Вперёд", callback_data="random:next"),
            ],
            [InlineKeyboardButton(text="🏷 Показать теги", callback_data="random:tags")],
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="random:main")],
        ]
    )


def random_tags_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⭐ Сохранить", callback_data="random:save")],
            [InlineKeyboardButton(text="🖼 Вернуться к арту", callback_data="random:artwork")],
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="random:main")],
        ]
    )
