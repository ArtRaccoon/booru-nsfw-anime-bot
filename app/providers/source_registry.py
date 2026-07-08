from __future__ import annotations

import asyncio
import json
import logging
import time
from collections.abc import Iterable
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.providers.catalog import CatalogEntry, fetch_catalog, infer_engine
from app.providers.prober import ProbeResult, probe_candidate

logger = logging.getLogger("registry")

REGISTRY_PATH = Path("data/source_registry.json")
STATUS_AVAILABLE = "AVAILABLE"
STATUS_BROKEN = "BROKEN"
STATUS_AUTH_REQUIRED = "AUTH_REQUIRED"
STATUS_NO_API = "NO_API"
STATUS_TIMEOUT = "TIMEOUT"
STATUS_UNKNOWN = "UNKNOWN"

_STATUS_MAP = {
    "available": STATUS_AVAILABLE,
    "auth_required": STATUS_AUTH_REQUIRED,
    "forbidden": STATUS_AUTH_REQUIRED,
    "no_api": STATUS_NO_API,
    "timeout": STATUS_TIMEOUT,
    "broken": STATUS_BROKEN,
    "error": STATUS_BROKEN,
    "invalid_response": STATUS_BROKEN,
    "unsupported": STATUS_UNKNOWN,
    "unchecked": STATUS_UNKNOWN,
}


@dataclass(slots=True)
class SourceRecord:
    id: str
    name: str
    engine: str
    base_url: str
    api_url: str | None = None
    enabled: bool = False
    available: str = STATUS_UNKNOWN
    requires_auth: bool = False
    no_api: bool = False
    last_check: str | None = None
    response_time: float | None = None
    success_rate: float = 0.0
    posts_received: int = 0
    last_error: str | None = None
    priority: int = 100
    checks_total: int = 0
    checks_success: int = 0
    extra: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_catalog(cls, entry: CatalogEntry) -> SourceRecord:
        return cls(
            id=entry.slug,
            name=entry.name,
            engine=infer_engine(entry.base_url, entry.notes),
            base_url=entry.base_url,
            api_url=entry.api_url,
            requires_auth=entry.requires_auth,
            no_api=False,
            last_error="marked broken in catalog" if entry.broken else None,
            extra={"source": entry.source, "notes": entry.notes, "sfw_status": entry.sfw_status},
        )


class SourceRegistry:
    def __init__(self, path: Path | str = REGISTRY_PATH) -> None:
        self.path = Path(path)
        self.sources: dict[str, SourceRecord] = {}
        self._stop_event = asyncio.Event()

    def load(self) -> SourceRegistry:
        if not self.path.exists():
            self.sources = {}
            return self
        raw = json.loads(self.path.read_text())
        records = raw.get("sources", raw if isinstance(raw, list) else [])
        self.sources = {item["id"]: SourceRecord(**item) for item in records}
        return self

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"version": 1, "sources": [asdict(s) for s in self.sources.values()]}
        self.path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))

    def enable(self, source_id: str) -> bool:
        if source_id not in self.sources:
            return False
        self.sources[source_id].enabled = True
        self.save()
        return True

    def disable(self, source_id: str) -> bool:
        if source_id not in self.sources:
            return False
        self.sources[source_id].enabled = False
        self.save()
        return True

    def enable_all(self, available_only: bool = False) -> int:
        count = 0
        for s in self.sources.values():
            if available_only and s.available != STATUS_AVAILABLE:
                continue
            s.enabled = True
            count += 1
        self.save()
        return count

    def disable_all(self) -> int:
        for s in self.sources.values():
            s.enabled = False
        self.save()
        return len(self.sources)

    async def import_catalog(self, url: str | None = None, **kwargs: Any) -> dict[str, int]:
        entries = await fetch_catalog(*([url] if url else []), **kwargs)
        return self.import_entries(entries)

    def import_entries(self, entries: Iterable[CatalogEntry]) -> dict[str, int]:
        imported = updated = 0
        for entry in entries:
            rec = SourceRecord.from_catalog(entry)
            if rec.id in self.sources:
                old = self.sources[rec.id]
                rec.enabled = old.enabled
                rec.available = old.available
                rec.last_check = old.last_check
                rec.response_time = old.response_time
                rec.success_rate = old.success_rate
                rec.posts_received = old.posts_received
                rec.checks_total = old.checks_total
                rec.checks_success = old.checks_success
                updated += 1
            else:
                imported += 1
            self.sources[rec.id] = rec
        self.save()
        return {"imported": imported, "updated": updated, "total": len(self.sources)}

    async def check(
        self,
        *,
        concurrency: int = 25,
        source_ids: Iterable[str] | None = None,
        proxy_url: str | None = None,
        timeout: int = 10,
        user_agent: str = "booru-nsfw-anime-bot/0.1",
    ) -> dict[str, int]:
        ids = list(source_ids or self.sources.keys())
        sem = asyncio.Semaphore(max(1, concurrency))
        counts: dict[str, int] = {}
        self._stop_event.clear()

        async def one(source_id: str) -> None:
            if self._stop_event.is_set():
                return
            async with sem:
                rec = self.sources[source_id]
                start = time.perf_counter()
                try:
                    result = await probe_candidate(
                        rec.base_url,
                        rec.engine,
                        proxy_url=proxy_url,
                        timeout=timeout,
                        user_agent=user_agent,
                    )
                except Exception as exc:
                    result = ProbeResult(
                        "error", engine=rec.engine, error=f"{type(exc).__name__}: {exc}"[:500]
                    )
                self._apply_probe(rec, result, time.perf_counter() - start)
                counts[rec.available] = counts.get(rec.available, 0) + 1

        await asyncio.gather(*(one(i) for i in ids if i in self.sources))
        self.save()
        return counts

    def stop_check(self) -> None:
        self._stop_event.set()

    def _apply_probe(self, rec: SourceRecord, result: ProbeResult, elapsed: float) -> None:
        status = _STATUS_MAP.get(result.availability_status, STATUS_UNKNOWN)
        rec.available = status
        rec.last_check = datetime.now(UTC).replace(microsecond=0).isoformat()
        rec.response_time = round(elapsed, 3)
        rec.requires_auth = status == STATUS_AUTH_REQUIRED
        rec.no_api = status == STATUS_NO_API
        rec.last_error = result.error
        rec.engine = result.engine or rec.engine
        rec.checks_total += 1
        if status == STATUS_AVAILABLE:
            rec.checks_success += 1
        rec.success_rate = rec.checks_success / max(1, rec.checks_total)

    def stats(self) -> dict[str, int]:
        data = {
            "total": len(self.sources),
            "enabled": sum(1 for s in self.sources.values() if s.enabled),
        }
        for s in self.sources.values():
            data[s.available.lower()] = data.get(s.available.lower(), 0) + 1
            if s.no_api:
                data["no_api"] = data.get("no_api", 0) + 1
            if s.requires_auth:
                data["auth_required"] = data.get("auth_required", 0) + 1
        return data
