from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

import pytest
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.exceptions import TelegramBadRequest

from app.bot import _aiogram_proxy_url, build_dispatcher, create_bot
from app.config import Settings
from app.handlers import favorites as favorites_handler
from app.handlers import random_art as random_handler
from app.handlers.start import (
    MAIN_MENU_TEXT,
    MENU_PREMIUM_TEXT,
    PREMIUM_ACTIVATED_TEXT,
    PREMIUM_TEXT,
    SEARCH_HINT_TEXT,
    SEARCH_PROMPT_TEXT,
    START_TEXT,
    main_menu_stub,
    parse_search_tags,
    premium_main_menu,
    premium_open,
    premium_plan_selected,
    premium_successful_payment,
    search_main_menu,
    search_open,
    search_start,
    search_text_received,
    search_user_states,
    start,
)
from app.keyboards import (
    favorites_art_keyboard,
    favorites_empty_keyboard,
    favorites_tags_keyboard,
    main_menu_keyboard,
    premium_keyboard,
    random_art_keyboard,
    random_tags_keyboard,
    search_keyboard,
    search_prompt_keyboard,
    search_results_keyboard,
)
from app.loading import LOADING_FRAMES, show_loading
from app.premium import (
    PREMIUM_PLANS,
    PremiumState,
    TelegramStarsInvoiceService,
    is_premium_active,
    pending_premium_plans,
    premium_states,
)
from app.random_art import (
    DEFAULT_PROVIDERS,
    Artwork,
    RandomArtService,
    StaticArtworkProvider,
    format_tags_text,
)


def test_settings_load_defaults():
    settings = Settings(BOT_TOKEN="", PROXY_URL="")

    assert settings.bot_token == ""
    assert settings.proxy_url is None


@pytest.mark.parametrize(
    "proxy_url", ["socks5://127.0.0.1:1080", "socks5h://127.0.0.1:1080"]
)
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
        self.deletes = 0
        self.sent_messages = []
        self.fail_edit_text = False
        self.fail_edit_caption = False

    async def answer(self, text, **kwargs):
        self.answers.append((text, kwargs))
        sent = FakeMessage()
        sent.answers = self.answers
        self.sent_messages.append(sent)
        return sent

    async def edit_text(self, text, **kwargs):
        if self.fail_edit_text:
            raise TelegramBadRequest(
                method=None, message="there is no text in the message to edit"
            )
        self.edits.append((text, kwargs))

    async def delete(self):
        self.deletes += 1

    async def answer_photo(self, photo, **kwargs):
        self.answers.append((photo, kwargs))

    async def edit_media(self, media, **kwargs):
        self.edits.append((media, kwargs))

    async def edit_caption(self, caption=None, **kwargs):
        if self.fail_edit_caption:
            raise TelegramBadRequest(method=None, message="message can't be edited")
        self.edits.append((caption, kwargs))


class FakeCallback:
    from_user = FakeUser()

    def __init__(self, data="search:start"):
        self.data = data
        self.answers = []
        self.message = FakeMessage()
        self.bot = object()

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


def test_premium_menu_opens():
    call = FakeCallback("menu:premium")

    asyncio.run(premium_open(call))

    assert call.message.edits[0][0] == PREMIUM_TEXT
    assert call.message.edits[0][1]["reply_markup"] == premium_keyboard()
    assert call.answers == [(None, {})]


def test_main_menu_stub_compat_opens_premium_menu():
    call = FakeCallback("menu:premium")

    asyncio.run(main_menu_stub(call))

    assert call.message.edits[0][0] == MENU_PREMIUM_TEXT


def test_premium_buttons_exist():
    buttons = _buttons(premium_keyboard())

    assert [(button.text, button.callback_data) for button in buttons] == [
        ("⭐ 1 день", "premium:day"),
        ("⭐ 7 дней", "premium:week"),
        ("⭐ 30 дней", "premium:month"),
        ("🏠 Главное меню", "premium:main"),
    ]


def test_premium_main_menu_returns():
    call = FakeCallback("premium:main")

    asyncio.run(premium_main_menu(call))

    assert call.message.edits[0][0] == MAIN_MENU_TEXT
    assert call.message.edits[0][1]["reply_markup"] == main_menu_keyboard()
    assert call.answers == [(None, {})]


class FakePremiumInvoiceService:
    def __init__(self):
        self.calls = []

    async def create_invoice(self, bot, user_id, plan, payload):
        self.calls.append((bot, user_id, plan, payload))


class FakeSuccessfulPayment:
    def __init__(self, invoice_payload):
        self.invoice_payload = invoice_payload


def test_premium_invoice_creation_called_with_xtr_plan(monkeypatch):
    pending_premium_plans.clear()
    service = FakePremiumInvoiceService()
    from app.handlers import start as start_handler

    monkeypatch.setattr(start_handler, "premium_invoice_service", service)
    call = FakeCallback("premium:day")

    asyncio.run(premium_plan_selected(call))

    assert len(service.calls) == 1
    _, user_id, plan, payload = service.calls[0]
    assert user_id == 42
    assert plan.code == "day"
    assert plan.stars == 50
    assert pending_premium_plans[payload].plan == "day"


class FakeInvoiceBot:
    def __init__(self):
        self.invoices = []

    async def send_invoice(self, **kwargs):
        self.invoices.append(kwargs)


def test_telegram_stars_invoice_service_uses_xtr_currency():
    bot = FakeInvoiceBot()
    service = TelegramStarsInvoiceService()

    asyncio.run(service.create_invoice(bot, 42, PREMIUM_PLANS["month"], "payload"))

    assert bot.invoices[0]["currency"] == "XTR"
    assert bot.invoices[0]["prices"][0].amount == 700


def test_successful_payment_activates_premium():
    pending_premium_plans.clear()
    premium_states.clear()
    payload = "premium:42:week:test"
    pending_premium_plans[payload] = __import__(
        "app.premium", fromlist=["PendingPremiumPlan"]
    ).PendingPremiumPlan(user_id=42, plan="week", created_at=datetime.now(UTC))
    message = FakeMessage()
    message.successful_payment = FakeSuccessfulPayment(payload)

    asyncio.run(premium_successful_payment(message))

    assert premium_states[42].plan == "week"
    assert premium_states[42].premium_until > datetime.now(UTC) + timedelta(days=6)
    assert message.answers == [(PREMIUM_ACTIVATED_TEXT, {})]


def test_expired_premium_returns_false():
    premium_states.clear()
    premium_states[42] = PremiumState(
        user_id=42,
        premium_until=datetime.now(UTC) - timedelta(seconds=1),
        plan="day",
        created_at=datetime.now(UTC) - timedelta(days=1),
    )

    assert is_premium_active(42) is False


def test_active_premium_returns_true():
    premium_states.clear()
    premium_states[42] = PremiumState(
        user_id=42,
        premium_until=datetime.now(UTC) + timedelta(seconds=60),
        plan="day",
        created_at=datetime.now(UTC),
    )

    assert is_premium_active(42) is True


def test_menu_search_opens_search_prompt():
    search_user_states.clear()
    call = FakeCallback("menu:search")

    asyncio.run(search_open(call))

    assert call.message.edits[0][0] == SEARCH_PROMPT_TEXT
    assert call.message.edits[0][1]["reply_markup"] == search_prompt_keyboard()
    assert search_user_states[42] == "waiting_for_search_tags"
    assert call.answers == [(None, {})]


def test_search_prompt_has_main_menu_button():
    buttons = _buttons(search_prompt_keyboard())

    assert [(button.text, button.callback_data) for button in buttons] == [
        ("🏠 Главное меню", "search:main")
    ]


@pytest.mark.parametrize(
    ("raw_text", "expected_tags"),
    [
        ("landscape, sunset, long hair", ["landscape", "sunset", "long_hair"]),
        ("TAG1, Tag Two", ["tag1", "tag_two"]),
        ("tag1, , tag2,,  ", ["tag1", "tag2"]),
    ],
)
def test_parse_search_tags(raw_text, expected_tags):
    assert parse_search_tags(raw_text) == expected_tags


def test_search_text_shows_parsed_tags_preview_and_clears_state(monkeypatch):
    search_user_states.clear()
    search_user_states[42] = "waiting_for_search_tags"
    service = RandomArtService(
        [SequenceProvider([_art("search-1", ("landscape", "sunset", "long_hair"))])]
    )
    monkeypatch.setattr("app.handlers.start.random_art_service", service)
    message = FakeMessage()
    message.text = "landscape, sunset, long hair"

    asyncio.run(search_text_received(message))

    assert message.answers[-1][0] == "https://example.test/search-1.jpg"
    assert message.answers[-1][1]["caption"] == random_handler.RANDOM_TITLE
    assert message.answers[-1][1]["reply_markup"] == search_results_keyboard()
    assert 42 not in search_user_states


def test_search_results_keyboard_has_expected_buttons():
    buttons = _buttons(search_results_keyboard())

    assert [(button.text, button.callback_data) for button in buttons] == [
        ("⬅️ Назад", "search:previous"),
        ("⭐ Сохранить", "search:save"),
        ("➡️ Вперёд", "search:next"),
        ("🏷 Показать теги", "search:tags"),
        ("🏠 Главное меню", "search:main"),
    ]


def test_search_main_returns_to_main_menu():
    search_user_states.clear()
    search_user_states[42] = "waiting_for_search_tags"
    call = FakeCallback("search:main")

    asyncio.run(search_main_menu(call))

    assert call.message.edits[0][0] == MAIN_MENU_TEXT
    assert call.message.edits[0][1]["reply_markup"] == main_menu_keyboard()
    assert 42 not in search_user_states
    assert call.answers == [(None, {})]


def test_text_without_search_state_does_not_crash():
    search_user_states.clear()
    message = FakeMessage()
    message.text = "landscape"

    asyncio.run(search_text_received(message))

    assert message.answers == [(SEARCH_HINT_TEXT, {})]


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
        rating="safe",
        metadata={"internal": True},
    )


def test_random_viewer_opens(monkeypatch):
    service = RandomArtService([SequenceProvider([_art("1")])])
    monkeypatch.setattr(random_handler, "random_art_service", service)
    call = FakeCallback("menu:random")

    asyncio.run(random_handler.random_open(call))

    assert call.message.edits[-1][0] == "🦝 Енот Ищейка"
    assert call.message.answers[-1][0] == "https://example.test/1.jpg"
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

    assert call.answers[-1] == ("Это первый просмотренный арт.", {})


def test_back_does_not_fetch(monkeypatch):
    service = RandomArtService([SequenceProvider([_art("1"), _art("2")])])
    monkeypatch.setattr(random_handler, "random_art_service", service)
    asyncio.run(service.next_artwork(42))
    asyncio.run(service.next_artwork(42))
    call = FakeCallback("random:previous")

    asyncio.run(random_handler.random_previous(call))

    assert service.gallery(42).current.post_id == "1"
    assert service.providers[0]._queue == []
    assert call.message.edits[-1][0].media == "https://example.test/1.jpg"


def test_forward_uses_existing_history_before_fetching(monkeypatch):
    provider = SequenceProvider([_art("1"), _art("2"), _art("3")])
    service = RandomArtService([provider])
    monkeypatch.setattr(random_handler, "random_art_service", service)
    asyncio.run(service.next_artwork(42))
    asyncio.run(service.next_artwork(42))
    service.previous_artwork(42)
    call = FakeCallback("random:next")

    asyncio.run(random_handler.random_next(call))

    assert service.gallery(42).current.post_id == "2"
    assert [art.post_id for art in provider._queue] == ["3"]
    assert call.message.edits[-1][0].media == "https://example.test/2.jpg"


def test_no_unique_art_keeps_current_artwork_visible_and_answers(monkeypatch):
    first = _art("1")
    service = RandomArtService([SequenceProvider([first])])
    monkeypatch.setattr(random_handler, "random_art_service", service)
    asyncio.run(service.next_artwork(42))
    call = FakeCallback("random:next")

    asyncio.run(random_handler.random_next(call))

    assert service.gallery(42).current.post_id == "1"
    assert call.message.edits == []
    assert call.answers[-1] == ("Пока не нашла новый арт. Попробуйте ещё раз.", {})


def test_initial_empty_state_shows_main_menu_button(monkeypatch):
    service = RandomArtService([SequenceProvider([])])
    monkeypatch.setattr(random_handler, "random_art_service", service)
    call = FakeCallback("menu:random")

    asyncio.run(random_handler.random_open(call))

    assert call.message.edits[-1][0] == "Пока не удалось найти арт. Попробуйте позже."
    buttons = _buttons(call.message.edits[-1][1]["reply_markup"])
    assert [(button.text, button.callback_data) for button in buttons] == [
        ("🏠 Главное меню", "random:main")
    ]


def test_static_pool_has_at_least_30_sfw_items():
    static_provider = DEFAULT_PROVIDERS[0]

    assert len(static_provider._artworks) >= 30
    assert all(art.rating == "safe" for art in static_provider._artworks)
    assert all(
        art.provider_id
        and art.post_id
        and art.file_url
        and art.preview_url
        and art.tags
        for art in static_provider._artworks
    )


def test_random_save_answers_saved_notification(monkeypatch):
    service = RandomArtService([SequenceProvider([_art("1")])])
    monkeypatch.setattr(random_handler, "random_art_service", service)
    asyncio.run(service.next_artwork(42))
    call = FakeCallback("random:save")

    asyncio.run(random_handler.random_save(call))

    assert call.answers == [("Сохранено ⭐", {})]
    assert call.message.answers == []
    assert call.message.edits == []


def test_favorite_duplicate_prevention(monkeypatch):
    service = RandomArtService([SequenceProvider([_art("1")])])
    monkeypatch.setattr(random_handler, "random_art_service", service)
    asyncio.run(service.next_artwork(42))
    call = FakeCallback("random:save")

    asyncio.run(random_handler.random_save(call))
    asyncio.run(random_handler.random_save(call))

    assert call.answers == [("Сохранено ⭐", {}), ("Уже в избранном ⭐", {})]
    assert call.message.answers == []
    assert call.message.edits == []
    assert len(service.gallery(42).favorites) == 1


def test_tags_formatting_preserves_all_tags_in_order():
    artwork = _art(
        "1", ("tag1", "tag2", "tag3", "tag4", "tag5", "tag6", "tag7", "tag8", "tag9")
    )

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
    assert (
        call.message.edits[-1][0]
        == "🦝 Енот Ищейка\n\n<blockquote expandable>a, b</blockquote>"
    )
    assert call.message.edits[-1][1]["parse_mode"] == "HTML"

    asyncio.run(random_handler.random_artwork(call))
    assert call.message.edits[-1][0].caption == "🦝 Енот Ищейка"


def test_return_to_main_menu_from_random():
    call = FakeCallback("random:main")

    asyncio.run(random_handler.random_main_menu(call))

    assert call.message.edits[0][0] == MAIN_MENU_TEXT
    assert call.message.edits[0][1]["reply_markup"] == main_menu_keyboard()


def test_return_to_main_menu_from_random_media_message():
    call = FakeCallback("random:main")
    call.message.fail_edit_text = True
    call.message.fail_edit_caption = True

    asyncio.run(random_handler.random_main_menu(call))

    assert call.message.deletes == 1
    assert call.message.answers == [
        (MAIN_MENU_TEXT, {"reply_markup": main_menu_keyboard()})
    ]
    assert call.answers == [(None, {})]


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


def _save_artworks(service, user_id=42, count=2):
    for _ in range(count):
        asyncio.run(service.next_artwork(user_id))
        assert service.save_current(user_id)


def test_favorites_open_empty_state(monkeypatch):
    service = RandomArtService([SequenceProvider([])])
    monkeypatch.setattr(favorites_handler, "random_art_service", service)
    call = FakeCallback("menu:favorites")

    asyncio.run(favorites_handler.favorites_open(call))

    assert call.message.edits[-1][0] == favorites_handler.EMPTY_FAVORITES_TEXT
    assert call.message.edits[-1][1]["reply_markup"] == favorites_empty_keyboard()


def test_favorites_open_first_saved_artwork(monkeypatch):
    service = RandomArtService([SequenceProvider([_art("1")])])
    monkeypatch.setattr(favorites_handler, "random_art_service", service)
    _save_artworks(service, count=1)
    call = FakeCallback("menu:favorites")

    asyncio.run(favorites_handler.favorites_open(call))

    assert call.message.edits[-1][0] == "🦝 Енот Ищейка"
    assert call.message.answers[-1][0] == "https://example.test/1.jpg"
    assert call.message.answers[-1][1]["caption"] == "🦝 Енот Ищейка"
    assert call.message.answers[-1][1]["reply_markup"] == favorites_art_keyboard()


def test_favorites_next_and_previous(monkeypatch):
    service = RandomArtService([SequenceProvider([_art("1"), _art("2")])])
    monkeypatch.setattr(favorites_handler, "random_art_service", service)
    _save_artworks(service, count=2)
    favorites_handler.favorites_index[42] = 0
    call = FakeCallback("favorites:next")

    asyncio.run(favorites_handler.favorites_next(call))
    assert favorites_handler.favorites_index[42] == 1
    assert call.message.edits[-1][0].media == "https://example.test/2.jpg"

    asyncio.run(favorites_handler.favorites_previous(call))
    assert favorites_handler.favorites_index[42] == 0
    assert call.message.edits[-1][0].media == "https://example.test/1.jpg"


def test_favorites_boundaries_notify(monkeypatch):
    service = RandomArtService([SequenceProvider([_art("1"), _art("2")])])
    monkeypatch.setattr(favorites_handler, "random_art_service", service)
    _save_artworks(service, count=2)
    call = FakeCallback("favorites:previous")

    favorites_handler.favorites_index[42] = 0
    asyncio.run(favorites_handler.favorites_previous(call))
    favorites_handler.favorites_index[42] = 1
    asyncio.run(favorites_handler.favorites_next(call))

    assert call.answers == [
        ("Это первый сохранённый арт.", {}),
        ("Это последний сохранённый арт.", {}),
    ]
    assert call.message.edits == []


def test_favorites_tags_formatting_and_return_to_artwork(monkeypatch):
    service = RandomArtService([SequenceProvider([_art("1", ("a", "b", "c"))])])
    monkeypatch.setattr(favorites_handler, "random_art_service", service)
    _save_artworks(service, count=1)
    favorites_handler.favorites_index[42] = 0
    call = FakeCallback("favorites:tags")

    asyncio.run(favorites_handler.favorites_tags(call))
    assert (
        call.message.edits[-1][0]
        == "🦝 Енот Ищейка\n\n<blockquote expandable>a, b, c</blockquote>"
    )
    assert call.message.edits[-1][1]["parse_mode"] == "HTML"
    assert call.message.edits[-1][1]["reply_markup"] == favorites_tags_keyboard()

    asyncio.run(favorites_handler.favorites_artwork(call))
    assert call.message.edits[-1][0].media == "https://example.test/1.jpg"


def test_favorites_delete_current_item(monkeypatch):
    service = RandomArtService([SequenceProvider([_art("1"), _art("2")])])
    monkeypatch.setattr(favorites_handler, "random_art_service", service)
    _save_artworks(service, count=2)
    favorites_handler.favorites_index[42] = 0
    call = FakeCallback("favorites:delete")

    asyncio.run(favorites_handler.favorites_delete(call))

    assert call.answers == [("Удалено из избранного", {})]
    assert [key[1] for key in service.gallery(42).favorites] == ["2"]
    assert call.message.edits[-1][0].media == "https://example.test/2.jpg"


def test_favorites_delete_last_item_shows_empty(monkeypatch):
    service = RandomArtService([SequenceProvider([_art("1")])])
    monkeypatch.setattr(favorites_handler, "random_art_service", service)
    _save_artworks(service, count=1)
    favorites_handler.favorites_index[42] = 0
    call = FakeCallback("favorites:delete")

    asyncio.run(favorites_handler.favorites_delete(call))

    assert call.message.edits[-1][0] == favorites_handler.EMPTY_FAVORITES_TEXT
    assert call.message.edits[-1][1]["reply_markup"] == favorites_empty_keyboard()


def test_favorites_main_menu_return_from_media_message_fallback():
    call = FakeCallback("favorites:main")
    call.message.fail_edit_text = True
    call.message.fail_edit_caption = True

    asyncio.run(favorites_handler.favorites_main(call))

    assert call.message.deletes == 1
    assert call.message.answers == [
        (MAIN_MENU_TEXT, {"reply_markup": main_menu_keyboard()})
    ]
    assert call.answers == [(None, {})]


def test_favorites_user_text_excludes_provider_source_and_rating(monkeypatch):
    service = RandomArtService(
        [SequenceProvider([_art("1", ("tag", "source", "safe"))])]
    )
    monkeypatch.setattr(favorites_handler, "random_art_service", service)
    _save_artworks(service, count=1)
    call = FakeCallback("menu:favorites")

    asyncio.run(favorites_handler.favorites_open(call))
    user_texts = [call.message.edits[-1][0], call.message.answers[-1][1]["caption"]]

    assert user_texts == ["🦝 Енот Ищейка", "🦝 Енот Ищейка"]
    assert all(
        "seq" not in text and "safe" not in text and "example.test" not in text
        for text in user_texts
    )


def test_search_cache_key_normalizes_tags():
    from app.random_art import search_cache_key

    assert search_cache_key(["long hair", " Sunset "]) == "long_hair,sunset"


def test_search_cache_expires_by_ttl():
    from app.random_art import ProviderCacheService

    now = 1000.0
    cache = ProviderCacheService(time_func=lambda: now)
    cache.put_search(["long hair"], [_art("cached")])
    assert cache.get_search(["long_hair"])[0].post_id == "cached"
    now += 1801
    assert cache.get_search(["long_hair"]) is None


def test_random_uses_cache_before_live_provider():
    provider = SequenceProvider([_art("live")])
    service = RandomArtService([provider])
    service.cache.random_sfw_pool.append(_art("cached"))

    artwork = asyncio.run(service.next_artwork(42))

    assert artwork.post_id == "cached"
    assert provider._queue[0].post_id == "live"


def test_cache_refill_triggers_below_threshold():
    class SearchAllProvider(SequenceProvider):
        async def search(self, tags, *, mode="sfw", limit=20, page=0):
            return self._artworks[:limit]

    service = RandomArtService([SearchAllProvider([_art("live")])])

    async def run():
        service.cache.maybe_trigger_refill(service.sfw_providers())
        await service.cache._refill_task

    asyncio.run(run())

    assert service.cache.random_sfw_pool


def test_provider_failure_sets_cooldown_and_skips():
    from app.random_art import ProviderCacheService

    cache = ProviderCacheService(time_func=lambda: 10.0)
    cache.set_cooldown("provider")

    assert cache.is_on_cooldown("provider") is True


def test_search_next_uses_cached_results_before_live_fetch():
    service = RandomArtService([SequenceProvider([_art("live", ("sunset",))])])
    service.cache.put_search(["sunset"], [_art("cached", ("sunset",))])

    assert asyncio.run(service.start_search(42, ["sunset"])).post_id == "cached"
    assert service.providers[0]._queue[0].post_id == "live"


def test_loading_helper_sends_temporary_message():
    call = FakeCallback("random:next")

    asyncio.run(show_loading(call, frames=(LOADING_FRAMES[0],)))

    assert call.message.answers == [(LOADING_FRAMES[0], {})]
    assert call.message.sent_messages[0].deletes == 1
    assert call.message.edits == []
    assert call.answers == [(None, {})]


def test_loading_helper_animates_temporary_message():
    call = FakeCallback("random:next")

    asyncio.run(show_loading(call, frames=(LOADING_FRAMES[0], LOADING_FRAMES[1])))

    assert call.message.answers == [(LOADING_FRAMES[0], {})]
    assert call.message.sent_messages[0].edits == [(LOADING_FRAMES[1], {})]


def test_loading_helper_does_not_crash_when_edit_fails():
    call = FakeCallback("random:next")

    async def failing_answer(*args, **kwargs):
        raise TelegramBadRequest(method=None, message="message can't be sent")

    call.message.answer = failing_answer

    asyncio.run(show_loading(call, frames=(LOADING_FRAMES[2],)))

    assert call.answers == [(None, {}), ("Ищу арт…", {})]


def test_random_next_calls_loading_before_final_render(monkeypatch):
    service = RandomArtService([SequenceProvider([_art("1"), _art("2")])])
    monkeypatch.setattr(random_handler, "random_art_service", service)
    asyncio.run(service.next_artwork(42))
    call = FakeCallback("random:next")

    asyncio.run(random_handler.random_next(call))

    assert call.message.answers[0][0] == LOADING_FRAMES[0]
    assert call.message.edits[-1][0].media == "https://example.test/2.jpg"


def test_search_next_calls_loading_before_final_render(monkeypatch):
    service = RandomArtService(
        [SequenceProvider([_art("1", ("sunset",)), _art("2", ("sunset",))])]
    )
    monkeypatch.setattr("app.handlers.start.random_art_service", service)
    asyncio.run(service.start_search(42, ["sunset"]))
    call = FakeCallback("search:next")

    from app.handlers import start as start_handler

    asyncio.run(start_handler.search_next(call))

    assert call.message.answers[0][0] == LOADING_FRAMES[0]
    assert call.message.edits[-1][0].media == "https://example.test/2.jpg"


def test_favorites_next_calls_loading_before_final_render(monkeypatch):
    service = RandomArtService([SequenceProvider([_art("1"), _art("2")])])
    monkeypatch.setattr(favorites_handler, "random_art_service", service)
    _save_artworks(service, count=2)
    favorites_handler.favorites_index[42] = 0
    call = FakeCallback("favorites:next")

    asyncio.run(favorites_handler.favorites_next(call))

    assert call.message.answers[0][0] == LOADING_FRAMES[0]
    assert call.message.edits[-1][0].media == "https://example.test/2.jpg"


def test_save_tags_and_main_menu_do_not_call_loading(monkeypatch):
    service = RandomArtService([SequenceProvider([_art("1")])])
    monkeypatch.setattr(random_handler, "random_art_service", service)
    asyncio.run(service.next_artwork(42))
    save_call = FakeCallback("random:save")
    tags_call = FakeCallback("random:tags")
    menu_call = FakeCallback("random:main")

    asyncio.run(random_handler.random_save(save_call))
    asyncio.run(random_handler.random_tags(tags_call))
    asyncio.run(random_handler.random_main_menu(menu_call))

    assert all(edit[0] not in LOADING_FRAMES for edit in save_call.message.edits)
    assert all(edit[0] not in LOADING_FRAMES for edit in tags_call.message.edits)
    assert all(edit[0] not in LOADING_FRAMES for edit in menu_call.message.edits)


def test_start_clears_transient_search_state():
    search_user_states[42] = "waiting_for_search_tags"
    message = FakeMessage()

    asyncio.run(start(message))

    assert 42 not in search_user_states


@pytest.mark.parametrize(
    ("handler", "callback_data"),
    [
        (search_main_menu, "search:main"),
        (random_handler.random_main_menu, "random:main"),
        (favorites_handler.favorites_main, "favorites:main"),
        (premium_main_menu, "premium:main"),
    ],
)
def test_main_callbacks_clear_transient_state(handler, callback_data):
    search_user_states[42] = "waiting_for_search_tags"
    call = FakeCallback(callback_data)

    asyncio.run(handler(call))

    assert 42 not in search_user_states
    assert call.message.edits[-1][0] == MAIN_MENU_TEXT
    assert call.message.edits[-1][1]["reply_markup"] == main_menu_keyboard()


def test_open_search_main_open_search_send_tags_works(monkeypatch):
    search_user_states.clear()
    service = RandomArtService(
        [SequenceProvider([_art("search", ("landscape", "sunset"))])]
    )
    monkeypatch.setattr("app.handlers.start.random_art_service", service)
    first = FakeCallback("menu:search")
    main = FakeCallback("search:main")
    second = FakeCallback("menu:search")
    message = FakeMessage()
    message.text = "landscape, sunset"

    asyncio.run(search_open(first))
    asyncio.run(search_main_menu(main))
    asyncio.run(search_open(second))
    asyncio.run(search_text_received(message))

    assert message.answers[-1][0] == "https://example.test/search.jpg"
    assert all(answer[0] != SEARCH_HINT_TEXT for answer in message.answers)


def test_main_menu_return_from_media_does_not_duplicate_tiny_title():
    call = FakeCallback("random:main")
    call.message.fail_edit_text = True

    asyncio.run(random_handler.random_main_menu(call))

    assert call.message.deletes == 0
    assert call.message.answers == []
    assert call.message.edits == [
        (MAIN_MENU_TEXT, {"reply_markup": main_menu_keyboard()})
    ]
