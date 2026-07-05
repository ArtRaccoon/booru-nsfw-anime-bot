from typing import Any

from app.models import BooruPost
from app.providers.base import BaseProvider


class GelbooruProvider(BaseProvider):
    name = "gelbooru"

    async def search(self, tags: str, limit: int, page: int) -> list[BooruPost]:
        resp = await self.client.get(
            f"{self.base_url}/index.php",
            params={
                "page": "dapi",
                "s": "post",
                "q": "index",
                "json": "1",
                "tags": tags,
                "limit": limit,
                "pid": max(page - 1, 0),
            },
        )
        resp.raise_for_status()
        data = resp.json()
        posts = data.get("post", data) if isinstance(data, dict) else data
        return [self.normalize_post(item) for item in posts if item.get("file_url")]

    def normalize_post(self, raw: dict[str, Any]) -> BooruPost:
        post_id = str(raw.get("id", ""))
        return BooruPost(
            provider=self.name,
            post_id=post_id,
            file_url=raw.get("file_url", ""),
            preview_url=raw.get("preview_url") or raw.get("sample_url"),
            source_url=f"{self.base_url}/index.php?page=post&s=view&id={post_id}"
            if post_id
            else None,
            rating=raw.get("rating"),
            tags=str(raw.get("tags", "")).split(),
            score=int(raw.get("score", 0))
            if str(raw.get("score", "")).lstrip("-").isdigit()
            else None,
        )


class Rule34Provider(GelbooruProvider):
    name = "rule34"
