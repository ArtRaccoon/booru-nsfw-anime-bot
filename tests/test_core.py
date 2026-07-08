from __future__ import annotations

import asyncio

import pytest
from aiogram.client.session.aiohttp import AiohttpSession

from app.bot import _aiogram_proxy_url, build_dispatcher, create_bot
from app.config import Settings
from app.handlers.start import (
    MAIN_MENU_TEXT,
    MENU_FAVORITES_TEXT,
    MENU_PREMIUM_TEXT,
    MENU_RANDOM_TEXT,
    MENU_SEARCH_TEXT,
    START_TEXT,
    main_menu_stub,
    search_start,
    start,
)
from app.keyboards import main_menu_keyboard, search_keyboard


def test_settings_load_defaults():
    settings = Settings(BOT_TOKEN="", PROXY_URL="")

    assert settings.bot_token == ""
    assert settings.proxy_url is None


@pytest.mark.parametrize("proxy_url", ["socks5://127.0.0.1:1080", "socks5h://127.0.0.1:1080"])
def test_create_bot_uses_proxy_url(proxy_url):
    settings = Settings(BOT_TOKEN="123:abc", PROXY_URL=proxy_url)
    bot = create_bot(settings)
    try:
        assert isinstance(bot.session, AiohttpSession)
        assert bot.session._proxy == _aiogram_proxy_url(proxy_url)
    finally:
        asyncio.run(bot.session.close())


def test_create_bot_without_proxy_starts_with_default_session():
    bot = create_bot(Settings(BOT_TOKEN="123:abc"))
    try:
        assert isinstance(bot.session, AiohttpSession)
        assert bot.session._proxy is None
        assert build_dispatcher().sub_routers
    finally:
        asyncio.run(bot.session.close())


class FakeUser:
    id = 42


class FakeMessage:
    from_user = FakeUser()

    def __init__(self):
        self.answers = []
        self.edits = []

    async def answer(self, text, **kwargs):
        self.answers.append((text, kwargs))

    async def edit_text(self, text, **kwargs):
        self.edits.append((text, kwargs))


class FakeCallback:
    from_user = FakeUser()

    def __init__(self, data="search:start"):
        self.data = data
        self.answers = []
        self.message = FakeMessage()

    async def answer(self, text=None, **kwargs):
        self.answers.append((text, kwargs))


def _buttons(markup):
    return [button for row in markup.inline_keyboard for button in row]


def test_start_returns_expected_text():
    message = FakeMessage()

    asyncio.run(start(message))

    assert message.answers[0][0] == START_TEXT


def test_start_keyboard_contains_exactly_one_search_start_button():
    markup = search_keyboard()
    buttons = _buttons(markup)

    assert len(buttons) == 1
    assert buttons[0].text == "🔎 Отправиться на поиски"
    assert buttons[0].callback_data == "search:start"


def test_search_start_opens_main_menu():
    call = FakeCallback()

    asyncio.run(search_start(call))

    assert call.message.edits[0][0] == MAIN_MENU_TEXT
    assert _buttons(call.message.edits[0][1]["reply_markup"])
    assert call.answers == [(None, {})]


def test_main_menu_contains_exactly_four_expected_buttons():
    buttons = _buttons(main_menu_keyboard())

    assert len(buttons) == 4
    assert [button.callback_data for button in buttons] == [
        "menu:random",
        "menu:favorites",
        "menu:search",
        "menu:premium",
    ]


@pytest.mark.parametrize(
    ("callback_data", "expected_text"),
    [
        ("menu:random", MENU_RANDOM_TEXT),
        ("menu:favorites", MENU_FAVORITES_TEXT),
        ("menu:search", MENU_SEARCH_TEXT),
        ("menu:premium", MENU_PREMIUM_TEXT),
    ],
)
def test_main_menu_stub_callbacks_answer(callback_data, expected_text):
    call = FakeCallback(callback_data)

    asyncio.run(main_menu_stub(call))

    assert call.answers == [(expected_text, {})]
