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


def premium_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⭐ 1 день", callback_data="premium:day")],
            [InlineKeyboardButton(text="⭐ 7 дней", callback_data="premium:week")],
            [InlineKeyboardButton(text="⭐ 30 дней", callback_data="premium:month")],
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="premium:main")],
        ]
    )


def search_prompt_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="search:main")]
        ]
    )


def search_results_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="⬅️ Назад", callback_data="search:previous"),
                InlineKeyboardButton(text="⭐ Сохранить", callback_data="search:save"),
                InlineKeyboardButton(text="➡️ Вперёд", callback_data="search:next"),
            ],
            [InlineKeyboardButton(text="🏷 Показать теги", callback_data="search:tags")],
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="search:main")],
        ]
    )


def search_tags_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⭐ Сохранить", callback_data="search:save")],
            [InlineKeyboardButton(text="🖼 Вернуться к арту", callback_data="search:artwork")],
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="search:main")],
        ]
    )


def random_empty_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="random:main")]
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


def favorites_empty_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="favorites:main")]
        ]
    )


def favorites_art_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="⬅️ Назад", callback_data="favorites:previous"),
                InlineKeyboardButton(text="🗑 Удалить", callback_data="favorites:delete"),
                InlineKeyboardButton(text="➡️ Вперёд", callback_data="favorites:next"),
            ],
            [InlineKeyboardButton(text="🏷 Показать теги", callback_data="favorites:tags")],
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="favorites:main")],
        ]
    )


def favorites_tags_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🗑 Удалить", callback_data="favorites:delete")],
            [InlineKeyboardButton(text="🖼 Вернуться к арту", callback_data="favorites:artwork")],
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="favorites:main")],
        ]
    )
