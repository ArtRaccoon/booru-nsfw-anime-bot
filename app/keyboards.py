from math import ceil

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.ui.sessions import callback_data

PROVIDERS_PER_PAGE = 8


def age_gate_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ Мне есть 18+", callback_data="age:confirm")],
            [InlineKeyboardButton(text="❌ Выйти", callback_data="age:exit")],
        ]
    )


def main_menu_keyboard(is_admin: bool = False) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text="🎲 Случайный арт", callback_data="random")],
        [InlineKeyboardButton(text="🔎 Поиск", callback_data="search_input")],
        [InlineKeyboardButton(text="🧭 Источники", callback_data="providers_page:0")],
        [InlineKeyboardButton(text="⭐ Избранное", callback_data="favorites_page:0")],
        [InlineKeyboardButton(text="🕘 История", callback_data="history")],
        [InlineKeyboardButton(text="⚙️ Настройки", callback_data="settings")],
    ]
    if is_admin:
        rows.append([InlineKeyboardButton(text="🛠 Админка", callback_data="admin_menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def post_keyboard(key: str, page: int) -> InlineKeyboardMarkup:
    nav = []
    if page > 1:
        nav.append(InlineKeyboardButton(text="⬅️ Назад", callback_data=callback_data("prev", key)))
    nav.append(InlineKeyboardButton(text="➡️ Далее", callback_data=callback_data("next", key)))
    return InlineKeyboardMarkup(
        inline_keyboard=[
            nav,
            [
                InlineKeyboardButton(text="🔁 Ещё", callback_data=callback_data("repeat", key)),
                InlineKeyboardButton(
                    text="⭐ В избранное", callback_data=callback_data("fav", key)
                ),
            ],
            [
                InlineKeyboardButton(text="🧭 Источник", callback_data="providers_page:0"),
                InlineKeyboardButton(text="🏠 Меню", callback_data="main_menu"),
            ],
        ]
    )


def providers_keyboard(
    providers: list[str],
    selected: str | None = None,
    page: int = 0,
    *,
    include_disabled: bool = False,
) -> InlineKeyboardMarkup:
    total_pages = max(1, ceil(len(providers) / PROVIDERS_PER_PAGE))
    page = max(0, min(page, total_pages - 1))
    start = page * PROVIDERS_PER_PAGE
    visible = providers[start : start + PROVIDERS_PER_PAGE]
    rows = [
        [
            InlineKeyboardButton(
                text=f"✅ {slug}" if slug == selected else slug,
                callback_data=f"provider:{slug}",
            )
        ]
        for slug in visible
    ]
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="⬅️", callback_data=f"providers_page:{page - 1}"))
    if page < total_pages - 1:
        nav.append(InlineKeyboardButton(text="➡️", callback_data=f"providers_page:{page + 1}"))
    if nav:
        rows.append(nav)
    if include_disabled:
        rows.extend(
            [
                [
                    InlineKeyboardButton(
                        text="✅ Активные", callback_data="admin_providers:active"
                    ),
                    InlineKeyboardButton(
                        text="💤 Отключённые", callback_data="admin_providers:disabled"
                    ),
                ],
                [
                    InlineKeyboardButton(
                        text="🧩 Требуют авторизацию", callback_data="admin_providers:auth"
                    ),
                    InlineKeyboardButton(
                        text="💥 Сломанные", callback_data="admin_providers:broken"
                    ),
                ],
                [InlineKeyboardButton(text="🔄 Перезагрузить", callback_data="reload_providers")],
            ]
        )
    rows.append([InlineKeyboardButton(text="🏠 Меню", callback_data="main_menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def history_keyboard(queries: list[str]) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=q[:60], callback_data=f"history_repeat:{i}")]
        for i, q in enumerate(queries)
    ]
    rows.append([InlineKeyboardButton(text="🏠 Меню", callback_data="main_menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def favorite_keyboard(item_id: int, page: int, total: int) -> InlineKeyboardMarkup:
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="⬅️", callback_data=f"favorites_page:{page - 1}"))
    if page < total - 1:
        nav.append(InlineKeyboardButton(text="➡️", callback_data=f"favorites_page:{page + 1}"))
    rows = []
    if nav:
        rows.append(nav)
    rows.append(
        [InlineKeyboardButton(text="🗑 Удалить", callback_data=f"remove_favorite:{item_id}:{page}")]
    )
    rows.append([InlineKeyboardButton(text="🏠 Меню", callback_data="main_menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def settings_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🧭 Сменить источник", callback_data="providers_page:0")],
            [InlineKeyboardButton(text="🌐 Режим источников", callback_data="source_mode_menu")],
            [InlineKeyboardButton(text="🧹 Очистить историю", callback_data="clear_history")],
            [InlineKeyboardButton(text="🏠 Меню", callback_data="main_menu")],
        ]
    )


def admin_keyboard() -> InlineKeyboardMarkup:
    labels = [
        ("📊 Статистика", "admin_stats"),
        ("🏷 Статистика тегов", "admin_tag_stats"),
        ("👤 Теги пользователя", "admin_user_tags"),
        ("🔎 Поиски пользователя", "admin_user_searches"),
        ("📢 Постинг в канал", "admin_channel_posting"),
        ("🗂 Каталог источников", "admin_catalog"),
        ("🛰 Групповой постинг", "admin_channel_posting"),
        ("🧪 Тест источника", "admin_test_provider"),
        ("🔄 Перезагрузить источники", "reload_providers"),
        ("✅ Включить источник", "admin_enable_provider"),
        ("🚫 Отключить источник", "admin_disable_provider"),
        ("💤 Отключённые", "admin_providers:disabled"),
        ("💥 Сломанные", "admin_providers:broken"),
        ("🧩 Требуют авторизацию", "admin_providers:auth"),
        ("🏠 Меню", "main_menu"),
    ]
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=text, callback_data=data)] for text, data in labels
        ]
    )


def channel_posting_keyboard() -> InlineKeyboardMarkup:
    rows = [
        [("▶️ Включить", "channel_enable"), ("⏸ Выключить", "channel_disable")],
        [("🚀 Пост сейчас", "channel_post_now"), ("🧪 Тест канала", "channel_test")],
        [("🎚 Режим", "channel_mode"), ("🏷 Теги", "channel_tags")],
        [("🌐 Источник", "channel_provider:0"), ("🌐 Стратегия источников", "channel_strategy")],
        [("⏱ Интервал", "channel_interval")],
        [("📜 История", "channel_history"), ("🧹 Сброс истории", "channel_reset_history")],
        [("🔗 Привязать", "channel_bind"), ("🏠 Меню", "admin_menu")],
    ]
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=text, callback_data=data) for text, data in row]
            for row in rows
        ]
    )


def channel_mode_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="SFW", callback_data="channel_set_mode:sfw"),
                InlineKeyboardButton(text="NSFW", callback_data="channel_set_mode:nsfw"),
                InlineKeyboardButton(text="MIXED", callback_data="channel_set_mode:mixed"),
            ],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_channel_posting")],
        ]
    )


def channel_provider_keyboard(
    slugs: list[str], page: int = 0, per_page: int = 8
) -> InlineKeyboardMarkup:
    values = ["auto", *sorted(slugs)]
    page = max(0, page)
    chunk = values[page * per_page : (page + 1) * per_page]
    rows = [
        [InlineKeyboardButton(text=slug, callback_data=f"channel_set_provider:{slug}")]
        for slug in chunk
    ]
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="⬅️", callback_data=f"channel_provider:{page - 1}"))
    if (page + 1) * per_page < len(values):
        nav.append(InlineKeyboardButton(text="➡️", callback_data=f"channel_provider:{page + 1}"))
    if nav:
        rows.append(nav)
    rows.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_channel_posting")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def group_posting_keyboard() -> InlineKeyboardMarkup:
    return channel_posting_keyboard()


def catalog_keyboard() -> InlineKeyboardMarkup:
    rows = [
        [("📥 Загрузить каталог", "catalog:import"), ("🧪 Проверить 25", "catalog:check_batch")],
        [("▶️ Продолжить", "catalog:resume"), ("🛑 Стоп", "catalog:stop")],
        [("✅ Доступные", "catalog:available"), ("💥 Недоступные", "catalog:broken")],
        [("🧬 По движку", "catalog:engine"), ("📊 Отчёт", "catalog:report")],
        [("✅ Включить доступные", "catalog:enable_available")],
        [("🔄 Перезагрузить реестр", "reload_providers"), ("🏠 Меню", "admin_menu")],
    ]
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=t, callback_data=d) for t, d in r] for r in rows
        ]
    )


def source_mode_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Один источник", callback_data="source_mode:selected")],
            [InlineKeyboardButton(text="По очереди", callback_data="source_mode:rotation")],
            [InlineKeyboardButton(text="Запасной перебор", callback_data="source_mode:fallback")],
            [InlineKeyboardButton(text="🏠 Меню", callback_data="main_menu")],
        ]
    )


def channel_strategy_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Один источник", callback_data="channel_set_strategy:selected"
                )
            ],
            [
                InlineKeyboardButton(
                    text="По очереди", callback_data="channel_set_strategy:round_robin"
                )
            ],
            [InlineKeyboardButton(text="Fallback", callback_data="channel_set_strategy:fallback")],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_channel_posting")],
        ]
    )
