import httpx

from app.bot import create_bot
from app.config import Settings
from app.models import BooruPost
from app.providers.base import BaseProvider


class DummyProvider(BaseProvider):
    name = "dummy"

    async def search(self, tags: str, limit: int, page: int) -> list[BooruPost]:
        return []

    def normalize_post(self, raw: dict) -> BooruPost:
        return BooruPost(provider=self.name, post_id="1", file_url="https://example.com/a.jpg")


def test_settings_parses_proxy_url_and_allows_empty():
    assert Settings(PROXY_URL="socks5://127.0.0.1:1080").proxy_url == "socks5://127.0.0.1:1080"
    assert Settings(PROXY_URL="").proxy_url is None


def test_create_bot_uses_proxy_session(monkeypatch):
    created = {}

    class FakeSession:
        def __init__(self, proxy):
            created["proxy"] = proxy

    class FakeBot:
        def __init__(self, token, session=None):
            created["token"] = token
            created["session"] = session

    monkeypatch.setattr("app.bot.AiohttpSession", FakeSession)
    monkeypatch.setattr("app.bot.Bot", FakeBot)

    bot = create_bot("123:test", "socks5://127.0.0.1:1080")

    assert bot is not None
    assert created["proxy"] == "socks5://127.0.0.1:1080"
    assert created["token"] == "123:test"
    assert isinstance(created["session"], FakeSession)


def test_provider_client_creation_accepts_proxy_url(monkeypatch):
    client_kwargs = {}

    class FakeAsyncClient:
        def __init__(self, **kwargs):
            client_kwargs.update(kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", FakeAsyncClient)

    DummyProvider("https://example.com", proxy_url="socks5://127.0.0.1:1080")

    assert client_kwargs["proxy"] == "socks5://127.0.0.1:1080"
    assert client_kwargs["follow_redirects"] is True
