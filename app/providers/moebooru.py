from __future__ import annotations

from app.models import Post
from app.providers.base import Provider, safe_json


class MoebooruProvider(Provider):
    name = "moebooru"
    base_url = ""

    async def search(self, tags: str = "", page: int = 1, limit: int = 20) -> list[Post]:
        async with self.client() as client:
            r = await client.get(
                f"{self.base_url}/post.json", params={"tags": tags, "page": page, "limit": limit}
            )
        data = safe_json(r)
        if not isinstance(data, list):
            return []
        out = []
        for item in data:
            url = item.get("file_url")
            if url and str(url).startswith("/"):
                url = self.base_url + url
            if url:
                out.append(
                    Post(
                        self.name,
                        str(item.get("id")),
                        url,
                        item.get("preview_url"),
                        f"{self.base_url}/post/show/{item.get('id')}",
                        item.get("rating"),
                        item.get("tags") or "",
                    )
                )
        return out


class YandereProvider(MoebooruProvider):
    name = "yandere"
    base_url = "https://yande.re"


class KonachanProvider(MoebooruProvider):
    name = "konachan"
    base_url = "https://konachan.com"


class SakugabooruProvider(MoebooruProvider):
    name = "sakugabooru"
    base_url = "https://www.sakugabooru.com"
