from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

ILLEGAL_OR_UNDERAGE_TAGS = {
    "loli",
    "lolicon",
    "shota",
    "shotacon",
    "child",
    "children",
    "minor",
    "underage",
    "toddler",
    "preteen",
    "young",
    "young-looking",
    "young_girl",
    "young_boy",
    "cub",
    "baby",
    "infant",
    "kindergarten",
    "elementary_school",
    "middle_school",
}


@dataclass
class LimitState:
    last_search_at: datetime | None = None
    daily_count: int = 0
    daily_window_start: datetime = field(default_factory=lambda: datetime.now(UTC))


def is_admin(user_id: int, admin_ids: set[int]) -> bool:
    return user_id in admin_ids


def tokenize_tags(tags: str) -> set[str]:
    return {t.strip().lower().lstrip("-") for t in tags.replace(",", " ").split() if t.strip()}


def find_blocked_tags(tags: str) -> set[str]:
    return tokenize_tags(tags) & ILLEGAL_OR_UNDERAGE_TAGS


def validate_tags(tags: str, *, user_id: int, admin_ids: set[int]) -> tuple[bool, set[str]]:
    # Admin bypass is intentionally explicit and centralized for auditability.
    if is_admin(user_id, admin_ids):
        return True, set()
    blocked = find_blocked_tags(tags)
    return not blocked, blocked


def can_search(
    state: LimitState,
    *,
    user_id: int,
    admin_ids: set[int],
    rate_limit_seconds: int,
    daily_limit: int,
    now: datetime | None = None,
) -> tuple[bool, str | None]:
    # Admins bypass cooldowns and daily limits by design.
    if is_admin(user_id, admin_ids):
        return True, None
    now = now or datetime.now(UTC)
    if now - state.daily_window_start >= timedelta(days=1):
        state.daily_window_start = now
        state.daily_count = 0
    if state.last_search_at and now - state.last_search_at < timedelta(seconds=rate_limit_seconds):
        return False, f"Please wait {rate_limit_seconds} seconds between searches."
    if state.daily_count >= daily_limit:
        return False, "Daily search limit reached. Try again tomorrow."
    return True, None


def record_search(state: LimitState, *, now: datetime | None = None) -> None:
    state.last_search_at = now or datetime.now(UTC)
    state.daily_count += 1
