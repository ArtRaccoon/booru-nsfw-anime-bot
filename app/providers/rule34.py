from __future__ import annotations

from app.providers.gelbooru import GelbooruProvider


class Rule34Provider(GelbooruProvider):
    name = "rule34"
    base_url = "https://api.rule34.xxx"
