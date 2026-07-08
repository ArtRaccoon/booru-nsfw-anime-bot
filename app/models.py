from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class Post:
    provider: str
    post_id: str
    file_url: str
    preview_url: str | None = None
    page_url: str | None = None
    rating: str | None = None
    tags: str = ""


@dataclass(slots=True)
class ProviderStatus:
    name: str
    ok: bool
    response_ms: int
    message: str = ""
