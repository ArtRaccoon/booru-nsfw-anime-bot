from __future__ import annotations

import time
from abc import ABC, abstractmethod
from typing import Any

import httpx

from app.models import Post, ProviderStatus


class Provider(ABC):
    name: str
    base_url: str

    def __init__(self, proxy_url: str | None = None, timeout: float = 12.0):
        self.proxy_url = proxy_url
        self.timeout = timeout

    def client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(proxy=self.proxy_url, timeout=self.timeout, follow_redirects=True)

    @abstractmethod
    async def search(self, tags: str = "", page: int = 1, limit: int = 20) -> list[Post]: ...

    async def random(self, tags: str = "") -> Post | None:
        posts = await self.search(tags=tags, page=1, limit=50)
        return posts[0] if posts else None

    async def healthcheck(self) -> ProviderStatus:
        start = time.perf_counter()
        try:
            posts = await self.search("", 1, 1)
            ms = int((time.perf_counter() - start) * 1000)
            return ProviderStatus(self.name, bool(posts), ms, "works" if posts else "empty")
        except Exception as exc:  # noqa: BLE001 - provider failures must not crash the bot
            ms = int((time.perf_counter() - start) * 1000)
            return ProviderStatus(self.name, False, ms, str(exc)[:120])


def safe_json(response: httpx.Response) -> Any | None:
    ctype = response.headers.get("content-type", "")
    if response.status_code >= 400 or "html" in ctype.lower():
        return None
    try:
        return response.json()
    except ValueError:
        return None
