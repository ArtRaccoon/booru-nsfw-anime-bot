from __future__ import annotations

import asyncio
import random
from dataclasses import dataclass
from typing import Any

import httpx

UA = "ArtRaccoonBooruBot/0.1 (+Telegram bot)"


@dataclass(slots=True)
class ProbeResult:
    availability_status: str
    http_status: int | None = None
    error: str | None = None
    engine: str | None = None


PROBES = {
    "danbooru": ["/posts.json?limit=1&tags=rating:safe"],
    "danbooru_old": ["/posts.json?limit=1&tags=rating:safe"],
    "moebooru": ["/posts.json?limit=1&tags=rating:safe"],
    "e621": ["/posts.json?limit=1&tags=rating:safe"],
    "e926": ["/posts.json?limit=1&tags=rating:safe"],
    "gelbooru_v02": ["/index.php?page=dapi&s=post&q=index&json=1&limit=1&tags=rating:safe"],
    "gelbooru_v01": ["/index.php?page=dapi&s=post&q=index&json=1&limit=1&tags=rating:safe"],
    "rule34": ["/index.php?page=dapi&s=post&q=index&json=1&limit=1&tags=rating:safe"],
    "philomena": ["/api/v1/json/search/images?q=safe&per_page=1"],
    "szurubooru": ["/api/posts/?query=rating:safe&limit=1"],
    "shimmie": ["/post/list/rating:safe/1?json=1", "/api/danbooru/find_posts/index.json?limit=1"],
    "unknown": ["/posts.json?limit=1", "/index.php?page=dapi&s=post&q=index&json=1&limit=1"],
}


def _classify_status(code: int) -> str:
    if code in {401, 407}:
        return "auth_required"
    if code == 403:
        return "forbidden"
    if code == 404:
        return "no_api"
    if code >= 500:
        return "broken"
    return "error"


async def probe_candidate(
    base_url: str,
    engine: str | None,
    *,
    proxy_url: str | None = None,
    timeout: int = 10,
    user_agent: str = UA,
) -> ProbeResult:
    engine = engine or "unknown"
    if engine not in PROBES:
        return ProbeResult("unsupported", engine=engine, error="No probe for engine")
    kwargs: dict[str, Any] = {
        "timeout": timeout,
        "follow_redirects": True,
        "headers": {"User-Agent": user_agent},
    }
    if proxy_url:
        kwargs["proxy"] = proxy_url
    async with httpx.AsyncClient(**kwargs) as client:
        last: ProbeResult | None = None
        for path in PROBES[engine][:2]:
            await asyncio.sleep(random.uniform(0.02, 0.12))
            url = base_url.rstrip("/") + path
            try:
                resp = await client.get(url)
            except httpx.TimeoutException as exc:
                return ProbeResult("timeout", error=str(exc), engine=engine)
            except httpx.HTTPError as exc:
                last = ProbeResult("error", error=str(exc), engine=engine)
                continue
            if resp.status_code == 200:
                try:
                    data = resp.json()
                except ValueError as exc:
                    last = ProbeResult("invalid_response", resp.status_code, str(exc), engine)
                    continue
                if isinstance(data, (list, dict)):
                    return ProbeResult("available", resp.status_code, engine=engine)
                last = ProbeResult(
                    "invalid_response", resp.status_code, "JSON root is not object/list", engine
                )
            else:
                last = ProbeResult(
                    _classify_status(resp.status_code), resp.status_code, resp.text[:300], engine
                )
        return last or ProbeResult("error", engine=engine)
