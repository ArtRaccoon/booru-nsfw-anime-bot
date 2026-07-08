from __future__ import annotations

from app.models import Post
from app.providers.base import Provider, safe_json


class DanbooruProvider(Provider):
    name = "danbooru"
    base_url = "https://danbooru.donmai.us"

    async def search(self, tags: str = "", page: int = 1, limit: int = 20) -> list[Post]:
        async with self.client() as client:
            r = await client.get(
                f"{self.base_url}/posts.json", params={"tags": tags, "page": page, "limit": limit}
            )
        data = safe_json(r)
        if not isinstance(data, list):
            return []
        posts = []
        for item in data:
            url = item.get("file_url") or item.get("large_file_url")
            if url:
                posts.append(
                    Post(
                        self.name,
                        str(item.get("id")),
                        url,
                        item.get("preview_file_url"),
                        f"{self.base_url}/posts/{item.get('id')}",
                        item.get("rating"),
                        item.get("tag_string") or "",
                    )
                )
        return posts


class SafebooruDonmaiProvider(DanbooruProvider):
    name = "safebooru_donmai"

    async def search(self, tags: str = "", page: int = 1, limit: int = 20) -> list[Post]:
        tags = f"rating:general {tags}".strip()
        return await super().search(tags, page, limit)
