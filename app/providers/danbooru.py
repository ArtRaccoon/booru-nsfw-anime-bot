from typing import Any

from app.models import BooruPost
from app.providers.base import BaseProvider


class DanbooruProvider(BaseProvider):
    name = "danbooru"

    async def search(self, tags: str, limit: int, page: int) -> list[BooruPost]:
        resp = await self.safe_get(
            f"{self.base_url}/posts.json", params={"tags": tags, "limit": limit, "page": page}
        )
        if resp is None:
            return []
        data = self.safe_json(resp)
        if not isinstance(data, list):
            return []
        return self.safe_normalize_many(data, ("file_url", "large_file_url"))

    def normalize_post(self, raw: dict[str, Any]) -> BooruPost:
        tags = raw.get("tag_string") or " ".join(raw.get("tags", []))
        post_id = str(raw.get("id", ""))
        return BooruPost(
            provider=self.name,
            post_id=post_id,
            file_url=raw.get("file_url") or raw.get("large_file_url") or "",
            preview_url=raw.get("preview_file_url"),
            source_url=f"{self.base_url}/posts/{post_id}" if post_id else raw.get("source"),
            rating=raw.get("rating"),
            tags=tags.split(),
            score=raw.get("score"),
        )
