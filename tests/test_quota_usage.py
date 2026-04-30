import time

from src.api.quota_usage import (
    get_quota_usage_snapshot,
    list_quota_usage_snapshots,
    record_request,
    reset_usage_for_tests,
    resolve_tier_from_role,
)


def setup_function():
    reset_usage_for_tests()


def test_resolve_tier_from_role_defaults():
    assert resolve_tier_from_role("viewer") == "free"
    assert resolve_tier_from_role("trader") == "basic"
    assert resolve_tier_from_role("developer") == "pro"
    assert resolve_tier_from_role("admin") == "pro"
    assert resolve_tier_from_role("") == "free"


def test_record_request_and_snapshot_counts():
    record_request(
        username="alice",
        tier="basic",
        path="/api/signals",
        method="GET",
        status_code=200,
    )
    record_request(
        username="alice",
        tier="basic",
        path="/api/strategies",
        method="GET",
        status_code=200,
    )

    snapshot = get_quota_usage_snapshot("alice", fallback_tier="free")

    assert snapshot["user"] == "alice"
    assert snapshot["tier"] == "basic"
    assert snapshot["requests"]["lastMinute"] == 2
    assert snapshot["requests"]["lastHour"] == 2
    assert snapshot["limits"]["perMinute"] > 0
    assert snapshot["limits"]["perHour"] > 0
    assert snapshot["lastRequest"]["path"] == "/api/strategies"


def test_list_quota_snapshots_sorted_by_latest_request():
    record_request(
        username="first-user",
        tier="free",
        path="/health",
        method="GET",
        status_code=200,
    )
    time.sleep(0.01)
    record_request(
        username="second-user",
        tier="pro",
        path="/api/system/migration-control-center",
        method="GET",
        status_code=200,
    )

    snapshots = list_quota_usage_snapshots(limit=10)

    assert len(snapshots) == 2
    assert snapshots[0]["user"] == "second-user"
    assert snapshots[1]["user"] == "first-user"
