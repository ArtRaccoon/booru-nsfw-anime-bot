from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlparse

import httpx

DEFAULT_CATALOG_URL = "https://raw.githubusercontent.com/red-tails/list-of-boorus/master/README.md"
KNOWN = {
    "danbooru.donmai.us": "danbooru",
    "gelbooru.com": "gelbooru_v02",
    "rule34.xxx": "rule34",
    "e621.net": "e621",
    "e926.net": "e926",
    "derpibooru.org": "philomena",
    "yande.re": "moebooru",
    "konachan.com": "moebooru",
}
SUPPORTED = {
    "danbooru",
    "danbooru_old",
    "gelbooru_v02",
    "gelbooru_v01",
    "moebooru",
    "shimmie",
    "philomena",
    "szurubooru",
    "e621",
    "e926",
    "rule34",
    "unknown",
}


@dataclass(slots=True)
class CatalogEntry:
    slug: str
    name: str
    base_url: str
    api_url: str | None = None
    engine: str = "unknown"
    category: str = "unknown"
    sfw_status: str = "unknown"
    anime_relevant: bool = False
    requires_auth: bool = False
    broken: bool = False
    source: str = "red-tails/list-of-boorus"
    notes: str = ""


def slugify(value: str) -> str:
    parsed = urlparse(value if "://" in value else "https://" + value)
    host = (parsed.netloc or parsed.path).lower().removeprefix("www.")
    slug = re.sub(r"[^a-z0-9]+", "_", host).strip("_")
    return slug or "unknown"


def infer_engine(url: str, metadata: str = "") -> str:
    text = f"{url} {metadata}".lower()
    host = urlparse(url if "://" in url else "https://" + url).netloc.lower().removeprefix("www.")
    for domain, engine in KNOWN.items():
        if domain in host:
            return engine
    if "philomena" in text or "booru-on-rails" in text or "derpibooru" in text:
        return "philomena"
    if "szurubooru" in text:
        return "szurubooru"
    if "shimmie" in text:
        return "shimmie"
    if "moebooru" in text or any(x in host for x in ("yande.re", "konachan")):
        return "moebooru"
    if "danbooru" in text:
        return "danbooru"
    if "gelbooru 0.1" in text:
        return "gelbooru_v01"
    if "gelbooru" in text or "rule34" in host:
        return "rule34" if "rule34" in host else "gelbooru_v02"
    if host in {"e621.net", "e926.net"}:
        return host.split(".", 1)[0]
    return "unknown"


def normalize_url(url: str) -> str:
    url = url.strip().rstrip("/.,)")
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    return url.rstrip("/")


def parse_catalog(text: str, source: str = "red-tails/list-of-boorus") -> list[CatalogEntry]:
    entries: dict[str, CatalogEntry] = {}
    # Accept Markdown links and bare URLs; upstream format changes over time.
    pairs = [
        (m.group(1), m.group(2)) for m in re.finditer(r"\[([^\]]+)\]\((https?://[^)\s]+)\)", text)
    ]
    pairs += [("", m.group(0)) for m in re.finditer(r"https?://[^\s<>)]+", text)]
    for name, raw_url in pairs:
        base_url = normalize_url(raw_url)
        parsed = urlparse(base_url)
        if (
            not parsed.netloc
            or "github.com" in parsed.netloc
            or "githubusercontent" in parsed.netloc
        ):
            continue
        slug = slugify(base_url)
        line = next((ln for ln in text.splitlines() if raw_url in ln), "")[:500]
        entry = CatalogEntry(
            slug=slug,
            name=(name.strip() or parsed.netloc.removeprefix("www.")).strip(),
            base_url=base_url,
            engine=infer_engine(base_url, line),
            anime_relevant=any(
                w in f"{base_url} {line}".lower()
                for w in ("anime", "danbooru", "gelbooru", "moe", "konachan", "yande")
            ),
            requires_auth="login" in line.lower() or "auth" in line.lower(),
            broken=any(w in line.lower() for w in ("dead", "offline", "broken")),
            source=source,
            notes=line,
        )
        entries.setdefault(slug, entry)
    return sorted(entries.values(), key=lambda e: e.slug)


async def fetch_catalog(
    url: str = DEFAULT_CATALOG_URL,
    *,
    proxy_url: str | None = None,
    user_agent: str = "ArtRaccoonBooruBot/0.1 (+Telegram bot)",
) -> list[CatalogEntry]:
    kwargs: dict[str, Any] = {
        "timeout": 30,
        "follow_redirects": True,
        "headers": {"User-Agent": user_agent},
    }
    if proxy_url:
        kwargs["proxy"] = proxy_url
    async with httpx.AsyncClient(**kwargs) as client:
        response = await client.get(url)
        response.raise_for_status()
    return parse_catalog(response.text)


def now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()
