from __future__ import annotations

import secrets
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from app.models import BooruPost

TTL = timedelta(minutes=30)
MAX_CALLBACK_DATA = 64


@dataclass
class SearchSession:
    user_id: int
    provider: str
    query: str
    page: int = 1
    image_message_id: int | None = None
    tags_message_ids: list[int] = field(default_factory=list)
    current_post_id: str | None = None
    current_page: int = 1
    current_provider: str = ""
    results: list[BooruPost] = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))


class CallbackSessions:
    def __init__(self, ttl: timedelta = TTL) -> None:
        self.ttl = ttl
        self._sessions: dict[str, SearchSession] = {}

    def create(self, session: SearchSession) -> str:
        self.cleanup()
        key = secrets.token_urlsafe(6)
        while key in self._sessions:
            key = secrets.token_urlsafe(6)
        self._sessions[key] = session
        return key

    def get(self, key: str, user_id: int) -> SearchSession | None:
        self.cleanup()
        session = self._sessions.get(key)
        if not session or session.user_id != user_id:
            return None
        if self._expired(session):
            self._sessions.pop(key, None)
            return None
        return session

    def update(self, key: str, session: SearchSession) -> None:
        self._sessions[key] = session

    def remove(self, key: str) -> None:
        self._sessions.pop(key, None)

    def cleanup(self) -> None:
        expired = [key for key, session in self._sessions.items() if self._expired(session)]
        for key in expired:
            self._sessions.pop(key, None)

    def _expired(self, session: SearchSession) -> bool:
        return datetime.now(UTC) - session.created_at > self.ttl


callback_sessions = CallbackSessions()


def callback_data(action: str, key: str) -> str:
    data = f"{action}:{key}"
    if len(data.encode()) > MAX_CALLBACK_DATA:
        raise ValueError("callback_data exceeds Telegram 64 byte limit")
    return data


def parse_callback(data: str | None) -> tuple[str, str] | None:
    if not data:
        return None
    action, sep, payload = data.partition(":")
    if not sep:
        return (data, "")
    return (action, payload)
