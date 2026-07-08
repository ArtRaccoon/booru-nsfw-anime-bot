from __future__ import annotations

import asyncio

import pytest
from aiogram.client.session.aiohttp import AiohttpSession

from app.bot import _aiogram_proxy_url, build_dispatcher, create_bot
from app.config import Settings
from app.handlers.start import SEARCH_UNDER_CONSTRUCTION_TEXT, START_TEXT, search_start, start
from app.keyboards import search_keyboard


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

    async def answer(self, text, **kwargs):
        self.answers.append((text, kwargs))


class FakeCallback:
    from_user = FakeUser()
    data = "search:start"

    def __init__(self):
        self.answers = []

    async def answer(self, text=None, **kwargs):
        self.answers.append((text, kwargs))


def test_start_returns_expected_text():
    message = FakeMessage()

    asyncio.run(start(message))

    assert message.answers[0][0] == START_TEXT


def test_keyboard_contains_exactly_one_button():
    markup = search_keyboard()
    buttons = [button for row in markup.inline_keyboard for button in row]

    assert len(buttons) == 1
    assert buttons[0].text == "🔎 Отправиться на поиски"
    assert buttons[0].callback_data == "search:start"


def test_search_start_callback_does_not_raise():
    call = FakeCallback()

    asyncio.run(search_start(call))

    assert call.answers == [(SEARCH_UNDER_CONSTRUCTION_TEXT, {})]
