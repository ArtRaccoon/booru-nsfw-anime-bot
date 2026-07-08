from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def kb(rows: list[list[tuple[str, str]]]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=t, callback_data=c) for t, c in row] for row in rows
        ]
    )


def main_menu(is_admin: bool = False) -> InlineKeyboardMarkup:
    rows = [
        [("🎲 Случайный арт", "random"), ("🔎 Поиск", "search")],
        [("🧭 Источники", "sources"), ("⭐ Избранное", "favorites")],
        [("🕘 История", "history"), ("⚙️ Настройки", "settings")],
    ]
    if is_admin:
        rows.append([("🛠 Админка", "admin")])
    return kb(rows)


def post_nav() -> InlineKeyboardMarkup:
    return kb(
        [
            [("⬅️ Назад", "prev"), ("➡️ Далее", "next"), ("🔁 Еще", "more")],
            [("⭐ В избранное", "fav_add"), ("🧭 Источник", "sources")],
            [("🏠 Меню", "menu")],
        ]
    )


def admin_menu() -> InlineKeyboardMarkup:
    return kb(
        [
            [("📊 Статистика", "admin_stats"), ("🧭 Источники", "admin_sources")],
            [
                ("📢 Постинг в канал", "admin_channel"),
                ("🧪 Проверить источники", "providers_check"),
            ],
            [("🏠 Меню", "menu")],
        ]
    )


def sources_menu(names: list[str]) -> InlineKeyboardMarkup:
    rows = [[(name, f"source:{name}")] for name in names]
    rows.append([("Авто-перебор", "source:auto"), ("🏠 Меню", "menu")])
    return kb(rows)
