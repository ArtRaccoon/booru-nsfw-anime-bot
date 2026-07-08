import logging
from abc import ABC, abstractmethod
from random import randint
from typing import Any

import httpx

from app.models import BooruPost
from app.providers.download import fetch_image_bytes
from app.providers.prober import ProbeResult

logger = logging.getLogger("providers")


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
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_url = api_url.rstrip("/") if api_url else None
        if name:
            self.name = name
        self._owns_client = client is None
        if client is not None:
            self.client = client
        else:
            limits = httpx.Limits(max_connections=50, max_keepalive_connections=20)
            timeout_config = httpx.Timeout(timeout, connect=min(timeout, 10.0))
            client_kwargs: dict[str, Any] = {
                "timeout": timeout_config,
                "follow_redirects": True,
                "limits": limits,
                "headers": {"User-Agent": "booru-nsfw-anime-bot/0.1"},
            }
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

    async def get_post(self, post_id: str) -> BooruPost | None:
        posts = await self.search(f"id:{post_id}", limit=1, page=1)
        return posts[0] if posts else None

    async def download(self, post: BooruPost) -> bytes:
        return await fetch_image_bytes(post.file_url, client=self.client, referer=self.base_url)

    async def healthcheck(self) -> ProbeResult:
        from app.providers.prober import probe_candidate

        return await probe_candidate(
            self.base_url, getattr(self, "engine", "unknown"), user_agent="booru-nsfw-anime-bot/0.1"
        )

    def safe_normalize_many(
        self, items: Any, url_keys: tuple[str, ...] = ("file_url",)
    ) -> list[BooruPost]:
        if not isinstance(items, list):
            return []
        posts: list[BooruPost] = []
        for item in items:
            if not isinstance(item, dict) or not any(item.get(key) for key in url_keys):
                continue
            try:
                posts.append(self.normalize_post(item))
            except Exception as exc:
                logger.warning("provider %s returned invalid post payload: %s", self.name, exc)
        return posts

    async def safe_get(self, url: str, **kwargs: Any) -> httpx.Response | None:
        for attempt in range(2):
            try:
                resp = await self.client.get(url, **kwargs)
                if resp.status_code in {401, 403, 404, 429} or resp.status_code >= 500:
                    logger.warning(
                        "provider %s returned HTTP %s for %s", self.name, resp.status_code, url
                    )
                    return None
                resp.raise_for_status()
                return resp
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                logger.warning(
                    "provider %s request failed on attempt %s: %s",
                    self.name,
                    attempt + 1,
                    exc,
                )
                if attempt == 0:
                    continue
            except httpx.HTTPStatusError as exc:
                logger.warning("provider %s HTTP error: %s", self.name, exc)
                return None
        return None

    def safe_json(self, resp: httpx.Response) -> Any:
        try:
            return resp.json()
        except ValueError as exc:
            logger.warning("provider %s returned invalid JSON: %s", self.name, exc)
            return []

    async def close(self) -> None:
        if self._owns_client:
            await self.client.aclose()
