from __future__ import annotations

import asyncio

import pytest
from aiogram.client.session.aiohttp import AiohttpSession

from app.bot import _aiogram_proxy_url, build_dispatcher, create_bot
from app.config import Settings
from app.handlers import random_art as random_handler
from app.handlers.start import (
    MAIN_MENU_TEXT,
    MENU_FAVORITES_TEXT,
    MENU_PREMIUM_TEXT,
    MENU_SEARCH_TEXT,
    START_TEXT,
    main_menu_stub,
    search_start,
    start,
)
from app.keyboards import (
    main_menu_keyboard,
    random_art_keyboard,
    random_tags_keyboard,
    search_keyboard,
)
from app.random_art import Artwork, RandomArtService, StaticArtworkProvider, format_tags_text


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

    async def answer_photo(self, photo, **kwargs):
        self.answers.append((photo, kwargs))

    async def edit_media(self, media, **kwargs):
        self.edits.append((media, kwargs))

    async def edit_caption(self, caption=None, **kwargs):
        self.edits.append((caption, kwargs))


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
        ("menu:favorites", MENU_FAVORITES_TEXT),
        ("menu:search", MENU_SEARCH_TEXT),
        ("menu:premium", MENU_PREMIUM_TEXT),
    ],
)
def test_main_menu_stub_callbacks_answer(callback_data, expected_text):
    call = FakeCallback(callback_data)

    asyncio.run(main_menu_stub(call))

    assert call.answers == [(expected_text, {})]


class SequenceProvider(StaticArtworkProvider):
    def __init__(self, artworks):
        super().__init__("seq", artworks)
        self._queue = list(artworks)

    async def random_sfw_artwork(self):
        return self._queue.pop(0) if self._queue else None


def _art(post_id, tags=("tag1", "tag2")):
    return Artwork(
        provider_id="seq",
        post_id=post_id,
        file_url=f"https://example.test/{post_id}.jpg",
        preview_url=f"https://example.test/{post_id}-preview.jpg",
        tags=tags,
        metadata={"internal": True},
    )


def test_random_viewer_opens(monkeypatch):
    service = RandomArtService([SequenceProvider([_art("1")])])
    monkeypatch.setattr(random_handler, "random_art_service", service)
    call = FakeCallback("menu:random")

    asyncio.run(random_handler.random_open(call))

    assert call.message.edits[0][0] == "🦝 Енот Ищейка"
    assert call.message.answers[0][0] == "https://example.test/1.jpg"
    assert service.gallery(42).current.post_id == "1"


def test_unique_artwork_selection_skips_duplicate():
    first = _art("1")
    second = _art("2")
    service = RandomArtService([SequenceProvider([first, first, second])])

    assert asyncio.run(service.next_artwork(42)) == first
    assert asyncio.run(service.next_artwork(42)) == second
    assert [art.post_id for art in service.gallery(42).history] == ["1", "2"]


def test_duplicate_prevention_returns_none_after_retries():
    first = _art("1")
    service = RandomArtService([SequenceProvider([first, *([first] * 15)])])

    assert asyncio.run(service.next_artwork(42)) == first
    assert asyncio.run(service.next_artwork(42)) is None
    assert [art.post_id for art in service.gallery(42).history] == ["1"]


def test_history_next_and_previous(monkeypatch):
    service = RandomArtService([SequenceProvider([_art("1"), _art("2")])])
    monkeypatch.setattr(random_handler, "random_art_service", service)
    asyncio.run(service.next_artwork(42))
    call = FakeCallback("random:next")

    asyncio.run(random_handler.random_next(call))
    assert service.gallery(42).current.post_id == "2"

    asyncio.run(random_handler.random_previous(call))
    assert service.gallery(42).current.post_id == "1"
    assert call.message.edits[-1][0].media == "https://example.test/1.jpg"


def test_history_previous_at_first_answers(monkeypatch):
    service = RandomArtService([SequenceProvider([_art("1")])])
    monkeypatch.setattr(random_handler, "random_art_service", service)
    asyncio.run(service.next_artwork(42))
    call = FakeCallback("random:previous")

    asyncio.run(random_handler.random_previous(call))

    assert call.answers == [("Это первый просмотренный арт.", {})]


def test_favorite_duplicate_prevention(monkeypatch):
    service = RandomArtService([SequenceProvider([_art("1")])])
    monkeypatch.setattr(random_handler, "random_art_service", service)
    asyncio.run(service.next_artwork(42))
    call = FakeCallback("random:save")

    asyncio.run(random_handler.random_save(call))
    asyncio.run(random_handler.random_save(call))

    assert call.answers == [(None, {}), ("Этот арт уже сохранён ⭐", {})]
    assert len(service.gallery(42).favorites) == 1


def test_tags_formatting_preserves_all_tags_in_order():
    artwork = _art("1", ("tag1", "tag2", "tag3", "tag4", "tag5", "tag6", "tag7", "tag8", "tag9"))

    assert format_tags_text(artwork) == (
        "🦝 Енот Ищейка\n\n"
        "<blockquote expandable>tag1, tag2, tag3, tag4, tag5, tag6, tag7, tag8, tag9</blockquote>"
    )


def test_show_tags_and_return_to_artwork(monkeypatch):
    service = RandomArtService([SequenceProvider([_art("1", ("a", "b"))])])
    monkeypatch.setattr(random_handler, "random_art_service", service)
    asyncio.run(service.next_artwork(42))
    call = FakeCallback("random:tags")

    asyncio.run(random_handler.random_tags(call))
    assert call.message.edits[-1][0] == "🦝 Енот Ищейка\n\n<blockquote expandable>a, b</blockquote>"
    assert call.message.edits[-1][1]["parse_mode"] == "HTML"

    asyncio.run(random_handler.random_artwork(call))
    assert call.message.edits[-1][0].caption == "🦝 Енот Ищейка"


def test_return_to_main_menu_from_random():
    call = FakeCallback("random:main")

    asyncio.run(random_handler.random_main_menu(call))

    assert call.message.edits[0][0] == MAIN_MENU_TEXT


def test_random_keyboards_have_expected_buttons():
    assert [button.callback_data for button in _buttons(random_art_keyboard())] == [
        "random:previous",
        "random:save",
        "random:next",
        "random:tags",
        "random:main",
    ]
    assert [button.callback_data for button in _buttons(random_tags_keyboard())] == [
        "random:save",
        "random:artwork",
        "random:main",
    ]
