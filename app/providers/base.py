from abc import ABC, abstractmethod
from random import randint
from typing import Any

import httpx

from app.models import BooruPost


class BaseProvider(ABC):
    name: str
    base_url: str

    def __init__(
        self,
        base_url: str,
        timeout: float = 15.0,
        proxy_url: str | None = None,
        name: str | None = None,
        api_url: str | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_url = api_url.rstrip("/") if api_url else None
        if name:
            self.name = name
        client_kwargs: dict[str, Any] = {"timeout": timeout, "follow_redirects": True}
        if proxy_url:
            client_kwargs["proxy"] = proxy_url
        self.client = httpx.AsyncClient(**client_kwargs)

    @abstractmethod
    async def search(self, tags: str, limit: int, page: int) -> list[BooruPost]: ...

    async def random(self, tags: str) -> BooruPost | None:
        posts = await self.search(tags, limit=1, page=randint(1, 100))
        return posts[0] if posts else None

    @abstractmethod
    def normalize_post(self, raw: dict[str, Any]) -> BooruPost: ...

    async def safe_get(self, url: str, **kwargs: Any) -> httpx.Response | None:
        try:
            resp = await self.client.get(url, **kwargs)
            resp.raise_for_status()
            return resp
        except (httpx.HTTPStatusError, httpx.TimeoutException, httpx.HTTPError):
            return None

    @staticmethod
    def safe_json(resp: httpx.Response) -> Any:
        try:
            return resp.json()
        except ValueError:
            return []

    async def close(self) -> None:
        await self.client.aclose()
