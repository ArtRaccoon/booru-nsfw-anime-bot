from __future__ import annotations

import hashlib
import logging
from io import BytesIO
from urllib.parse import urlparse

import httpx
from aiogram.types import BufferedInputFile

logger = logging.getLogger("download")
DEFAULT_IMAGE_TIMEOUT = 20.0
MAX_IMAGE_BYTES = 20 * 1024 * 1024


async def fetch_image_bytes(
    url: str,
    *,
    timeout: float = DEFAULT_IMAGE_TIMEOUT,
    max_bytes: int = MAX_IMAGE_BYTES,
    proxy_url: str | None = None,
) -> bytes:
    """Download media bytes with size guard for Telegram uploads."""
    limits = httpx.Limits(max_connections=20, max_keepalive_connections=10)
    client_kwargs = {
        "timeout": httpx.Timeout(timeout, connect=min(timeout, 10.0)),
        "follow_redirects": True,
        "limits": limits,
        "headers": {"User-Agent": "booru-nsfw-anime-bot/0.1"},
    }
    if proxy_url:
        client_kwargs["proxy"] = proxy_url
    async with httpx.AsyncClient(**client_kwargs) as client:
        async with client.stream("GET", url) as resp:
            resp.raise_for_status()
            buf = BytesIO()
            async for chunk in resp.aiter_bytes():
                buf.write(chunk)
                if buf.tell() > max_bytes:
                    raise ValueError("downloaded media exceeds max size")
            return buf.getvalue()


def _filename_from_url(url: str) -> str:
    path = urlparse(url).path
    name = path.rsplit("/", 1)[-1] or "booru_image.jpg"
    if "." not in name:
        name += ".jpg"
    return name[:120]


def as_buffered_input_file(data: bytes, url: str) -> BufferedInputFile:
    return BufferedInputFile(data, filename=_filename_from_url(url))


def content_hashes(data: bytes) -> dict[str, str]:
    return {"sha256": hashlib.sha256(data).hexdigest(), "md5": hashlib.md5(data).hexdigest()}
