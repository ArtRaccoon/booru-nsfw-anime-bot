from app.providers.danbooru import DanbooruProvider


class DanbooruOldProvider(DanbooruProvider):
    async def search(self, tags: str, limit: int, page: int):
        resp = await self.safe_get(
            f"{self.base_url}/post/index.json",
            params={"tags": tags, "limit": limit, "page": page},
        )
        if resp is None:
            return []
        data = self.safe_json(resp)
        if not isinstance(data, list):
            return []
        return self.safe_normalize_many(data, ("file_url", "large_file_url"))
