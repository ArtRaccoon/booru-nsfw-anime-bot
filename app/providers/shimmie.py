from typing import Any

from app.models import BooruPost
from app.providers.base import BaseProvider


class ShimmieProvider(BaseProvider):
    name = "shimmie"

    async def search(self, tags: str, limit: int, page: int) -> list[BooruPost]:
        endpoints = [
            ("/post/index.json", {"tags": tags, "limit": limit, "page": page}),
            ("/posts.json", {"tags": tags, "limit": limit, "page": page}),
            (
                "/index.php",
                {"q": "/post/list", "json": "1", "tags": tags, "limit": limit, "page": page},
            ),
        ]
        for path, params in endpoints:
            resp = await self.safe_get(f"{self.base_url}{path}", params=params)
            if resp is None:
                continue
            data = self.safe_json(resp)
            posts = data.get("posts", data.get("post", data)) if isinstance(data, dict) else data
            result = self.safe_normalize_many(posts, ("file_url", "image_url", "url"))
            if result:
                return result
        return []

    def normalize_post(self, raw: dict[str, Any]) -> BooruPost:
        post_id = str(raw.get("id", raw.get("post_id", "")))
        tags = raw.get("tags") or raw.get("tag_string") or ""
        tag_list = [str(t) for t in tags] if isinstance(tags, list) else str(tags).split()
        return BooruPost(
            provider=self.name,
            post_id=post_id,
            file_url=raw.get("file_url") or raw.get("image_url") or raw.get("url") or "",
            preview_url=raw.get("preview_url") or raw.get("thumb_url"),
            source_url=raw.get("source")
            or (f"{self.base_url}/post/view/{post_id}" if post_id else None),
            rating=raw.get("rating"),
            tags=tag_list,
            score=raw.get("score"),
        )
