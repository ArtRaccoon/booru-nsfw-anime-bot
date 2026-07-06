from typing import Any

from app.models import BooruPost
from app.providers.base import BaseProvider


class SzurubooruProvider(BaseProvider):
    async def search(self, tags: str, limit: int, page: int) -> list[BooruPost]:
        resp = await self.safe_get(
            f"{self.base_url}/api/posts",
            params={"query": tags, "pageSize": limit, "offset": max(page - 1, 0) * limit},
        )
        if resp is None:
            return []
        data = self.safe_json(resp)
        posts = data.get("results", []) if isinstance(data, dict) else []
        return [
            self.normalize_post(i) for i in posts if i.get("contentUrl") or i.get("content_url")
        ]

    def normalize_post(self, raw: dict[str, Any]) -> BooruPost:
        post_id = str(raw.get("id", ""))
        tags = raw.get("tags", [])
        names = [t.get("names", [""])[0] if isinstance(t, dict) else str(t) for t in tags]
        return BooruPost(
            provider=self.name,
            post_id=post_id,
            file_url=raw.get("contentUrl") or raw.get("content_url") or "",
            preview_url=raw.get("thumbnailUrl"),
            source_url=f"{self.base_url}/post/{post_id}" if post_id else None,
            rating=raw.get("safety"),
            tags=names,
            score=raw.get("score"),
        )
