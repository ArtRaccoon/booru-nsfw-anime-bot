from typing import Any

from app.models import BooruPost
from app.providers.base import BaseProvider


class PhilomenaProvider(BaseProvider):
    async def search(self, tags: str, limit: int, page: int) -> list[BooruPost]:
        resp = await self.safe_get(
            f"{self.base_url}/api/v1/json/search/images",
            params={"q": tags, "per_page": limit, "page": page},
        )
        if resp is None:
            return []
        data = self.safe_json(resp)
        images = data.get("images", []) if isinstance(data, dict) else []
        return [
            self.normalize_post(i)
            for i in images
            if i.get("representations", {}).get("full") or i.get("view_url")
        ]

    def normalize_post(self, raw: dict[str, Any]) -> BooruPost:
        post_id = str(raw.get("id", ""))
        reps = raw.get("representations", {})
        return BooruPost(
            provider=self.name,
            post_id=post_id,
            file_url=reps.get("full") or raw.get("view_url", ""),
            preview_url=reps.get("thumb"),
            source_url=f"{self.base_url}/images/{post_id}" if post_id else None,
            rating=None,
            tags=raw.get("tags", []),
            score=raw.get("score"),
        )
