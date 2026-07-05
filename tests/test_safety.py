from datetime import UTC, datetime

from app.safety import LimitState, can_search, find_blocked_tags, validate_tags


def test_blocks_underage_tags_for_regular_users():
    assert find_blocked_tags("anime loli rating:explicit") == {"loli"}
    ok, blocked = validate_tags("shota", user_id=1, admin_ids={2})
    assert not ok
    assert blocked == {"shota"}


def test_admin_bypasses_tag_filter():
    ok, blocked = validate_tags("loli shota", user_id=2, admin_ids={2})
    assert ok
    assert blocked == set()


def test_admin_bypasses_limits():
    state = LimitState(last_search_at=datetime.now(UTC), daily_count=999)
    ok, reason = can_search(
        state,
        user_id=2,
        admin_ids={2},
        rate_limit_seconds=8,
        daily_limit=50,
    )
    assert ok
    assert reason is None


def test_regular_user_daily_limit_applies():
    state = LimitState(daily_count=50)
    ok, reason = can_search(
        state,
        user_id=1,
        admin_ids={2},
        rate_limit_seconds=8,
        daily_limit=50,
    )
    assert not ok
    assert "Daily" in reason
