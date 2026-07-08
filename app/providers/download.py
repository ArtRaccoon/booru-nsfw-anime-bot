from __future__ import annotations

import hashlib
import logging
from io import BytesIO

import httpx
from aiogram.types import BufferedInputFile

logger = logging.getLogger("download")

DEFAULT_HEADERS = {"User-Agent": "booru-nsfw-anime-bot/0.1", "Accept": "image/*,*/*;q=0.8"}


def content_hashes(data: bytes) -> dict[str, str]:
    return {"sha256": hashlib.sha256(data).hexdigest(), "md5": hashlib.md5(data).hexdigest()}


async def fetch_image_bytes(
    url: str,
    *,
    client: httpx.AsyncClient | None = None,
    referer: str | None = None,
    timeout: float = 30.0,
    max_bytes: int = 25 * 1024 * 1024,
) -> bytes:
    headers = dict(DEFAULT_HEADERS)
    if referer:
        headers["Referer"] = referer
    owns = client is None
    if client is None:
        client = httpx.AsyncClient(timeout=timeout, follow_redirects=True, headers=headers)
    try:
        resp = await client.get(url, headers=headers)
        resp.raise_for_status()
        data = resp.content
        if len(data) > max_bytes:
            raise ValueError("image is too large")
        return data
    finally:
        if owns:
            await client.aclose()


def as_buffered_input_file(data: bytes, filename: str = "booru.jpg") -> BufferedInputFile:
    BytesIO(data)  # explicit in-memory pipeline marker for tests/readers
    return BufferedInputFile(data, filename=filename)
