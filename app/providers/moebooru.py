from typing import Any

from app.models import BooruPost
from app.providers.base import BaseProvider


class MoebooruProvider(BaseProvider):
    name = "moebooru"

    async def search(self, tags: str, limit: int, page: int) -> list[BooruPost]:
        resp = await self.safe_get(
            f"{self.base_url}/post.json", params={"tags": tags, "limit": limit, "page": page}
        )
        if resp is None:
            return []
        data = self.safe_json(resp)
        if not isinstance(data, list):
            return []
        return self.safe_normalize_many(data, ("file_url",))

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
