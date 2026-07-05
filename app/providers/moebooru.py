from typing import Any

from app.models import BooruPost
from app.providers.base import BaseProvider


class MoebooruProvider(BaseProvider):
    name = "moebooru"

    async def search(self, tags: str, limit: int, page: int) -> list[BooruPost]:
        resp = await self.client.get(
            f"{self.base_url}/post.json", params={"tags": tags, "limit": limit, "page": page}
        )
        resp.raise_for_status()
        return [self.normalize_post(item) for item in resp.json() if item.get("file_url")]

    def normalize_post(self, raw: dict[str, Any]) -> BooruPost:
        post_id = str(raw.get("id", ""))
        return BooruPost(
            provider=self.name,
            post_id=post_id,
            file_url=raw.get("file_url", ""),
            preview_url=raw.get("preview_url") or raw.get("sample_url"),
            source_url=f"{self.base_url}/post/show/{post_id}" if post_id else None,
            rating=raw.get("rating"),
            tags=str(raw.get("tags", "")).split(),
            score=raw.get("score"),
        )


class YandereProvider(MoebooruProvider):
    name = "yandere"


class KonachanProvider(MoebooruProvider):
    name = "konachan"
