from abc import ABC, abstractmethod
from random import randint
from typing import Any

import httpx

from app.models import BooruPost


class BaseProvider(ABC):
    name: str
    base_url: str

    def __init__(self, base_url: str, timeout: float = 15.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.client = httpx.AsyncClient(timeout=timeout, follow_redirects=True)

    @abstractmethod
    async def search(self, tags: str, limit: int, page: int) -> list[BooruPost]: ...

    async def random(self, tags: str) -> BooruPost | None:
        posts = await self.search(tags, limit=1, page=randint(1, 100))
        return posts[0] if posts else None

    @abstractmethod
    def normalize_post(self, raw: dict[str, Any]) -> BooruPost: ...

    async def close(self) -> None:
        await self.client.aclose()
