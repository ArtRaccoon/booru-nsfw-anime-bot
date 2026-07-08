from __future__ import annotations

from app.models import Post
from app.providers.base import Provider, safe_json


class GelbooruProvider(Provider):
    name = "gelbooru"
    base_url = "https://gelbooru.com"

    async def search(self, tags: str = "", page: int = 1, limit: int = 20) -> list[Post]:
        params = {
            "page": "dapi",
            "s": "post",
            "q": "index",
            "json": "1",
            "tags": tags,
            "pid": max(page - 1, 0),
            "limit": limit,
        }
        async with self.client() as client:
            r = await client.get(f"{self.base_url}/index.php", params=params)
        data = safe_json(r)
        items = (
            data.get("post", [])
            if isinstance(data, dict)
            else data
            if isinstance(data, list)
            else []
        )
        return [
            Post(
                self.name,
                str(i.get("id")),
                i.get("file_url"),
                i.get("preview_url"),
                f"{self.base_url}/index.php?page=post&s=view&id={i.get('id')}",
                i.get("rating"),
                i.get("tags") or "",
            )
            for i in items
            if i.get("file_url")
        ]
