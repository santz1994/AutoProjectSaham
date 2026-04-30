"""In-memory API quota usage tracker.

This module provides lightweight per-user usage counters for operational
visibility (minute/hour windows). It is intentionally process-local and is
used as an API-level monitoring helper, not as an enforcement mechanism.
"""
from __future__ import annotations

import os
import threading
import time
from collections import deque
from typing import Any, Deque, Dict, List

_LOCK = threading.RLock()
_USER_USAGE: Dict[str, Dict[str, Any]] = {}

_MINUTE_WINDOW_SECONDS = 60
_HOUR_WINDOW_SECONDS = 3600


def _env_int(name: str, default: int, minimum: int = 1) -> int:
    raw = str(os.getenv(name, "")).strip()
    if not raw:
        return max(minimum, int(default))
    try:
        return max(minimum, int(raw))
    except (TypeError, ValueError):
        return max(minimum, int(default))


def _quota_limits() -> Dict[str, Dict[str, int]]:
    return {
        "free": {
            "perMinute": _env_int("AUTOSAHAM_QUOTA_FREE_PER_MINUTE", 60),
            "perHour": _env_int("AUTOSAHAM_QUOTA_FREE_PER_HOUR", 1200),
        },
        "basic": {
            "perMinute": _env_int("AUTOSAHAM_QUOTA_BASIC_PER_MINUTE", 300),
            "perHour": _env_int("AUTOSAHAM_QUOTA_BASIC_PER_HOUR", 6000),
        },
        "pro": {
            "perMinute": _env_int("AUTOSAHAM_QUOTA_PRO_PER_MINUTE", 1200),
            "perHour": _env_int("AUTOSAHAM_QUOTA_PRO_PER_HOUR", 24000),
        },
    }


def _normalize_tier(tier: str) -> str:
    candidate = str(tier or "").strip().lower()
    if candidate in {"free", "basic", "pro"}:
        return candidate
    return "free"


def _normalize_username(username: str) -> str:
    candidate = str(username or "").strip().lower()
    if not candidate:
        return "anonymous"
    return candidate


def _parse_role_tier_mapping() -> Dict[str, str]:
    default_mapping = "viewer=free,trader=basic,developer=pro,admin=pro"
    raw = str(os.getenv("AUTOSAHAM_QUOTA_ROLE_TIERS", default_mapping)).strip()
    mapping: Dict[str, str] = {}

    for chunk in raw.split(","):
        pair = str(chunk or "").strip()
        if not pair or "=" not in pair:
            continue

        role, _, tier = pair.partition("=")
        role_key = str(role or "").strip().lower()
        tier_key = _normalize_tier(tier)
        if role_key:
            mapping[role_key] = tier_key

    if not mapping:
        mapping = {
            "viewer": "free",
            "trader": "basic",
            "developer": "pro",
            "admin": "pro",
        }

    return mapping


def resolve_tier_from_role(role: str) -> str:
    role_key = str(role or "").strip().lower()
    if not role_key:
        return "free"

    mapping = _parse_role_tier_mapping()
    return _normalize_tier(mapping.get(role_key, "free"))


def _prune_queue(queue: Deque[float], now_ts: float, window_seconds: int) -> None:
    lower_bound = float(now_ts) - float(window_seconds)
    while queue and queue[0] < lower_bound:
        queue.popleft()


def _queue_copy(queue: Deque[float]) -> Deque[float]:
    return deque(list(queue), maxlen=queue.maxlen)


def record_request(
    *,
    username: str,
    tier: str,
    path: str,
    method: str,
    status_code: int,
) -> None:
    now_ts = float(time.time())
    user_key = _normalize_username(username)
    tier_key = _normalize_tier(tier)

    with _LOCK:
        entry = _USER_USAGE.setdefault(
            user_key,
            {
                "tier": tier_key,
                "minuteTimestamps": deque(),
                "hourTimestamps": deque(),
                "lastRequest": None,
            },
        )

        minute_queue = entry.get("minuteTimestamps")
        if not isinstance(minute_queue, deque):
            minute_queue = deque()
            entry["minuteTimestamps"] = minute_queue

        hour_queue = entry.get("hourTimestamps")
        if not isinstance(hour_queue, deque):
            hour_queue = deque()
            entry["hourTimestamps"] = hour_queue

        _prune_queue(minute_queue, now_ts, _MINUTE_WINDOW_SECONDS)
        _prune_queue(hour_queue, now_ts, _HOUR_WINDOW_SECONDS)

        minute_queue.append(now_ts)
        hour_queue.append(now_ts)

        entry["tier"] = tier_key
        entry["lastRequest"] = {
            "path": str(path or "").strip() or "/",
            "method": str(method or "GET").strip().upper() or "GET",
            "statusCode": int(status_code),
            "timestamp": now_ts,
        }


def _build_snapshot(
    username: str,
    entry: Dict[str, Any],
    *,
    fallback_tier: str,
) -> Dict[str, Any]:
    now_ts = float(time.time())
    limits = _quota_limits()

    minute_queue_raw = entry.get("minuteTimestamps")
    hour_queue_raw = entry.get("hourTimestamps")

    minute_queue = minute_queue_raw if isinstance(minute_queue_raw, deque) else deque()
    hour_queue = hour_queue_raw if isinstance(hour_queue_raw, deque) else deque()

    minute_copy = _queue_copy(minute_queue)
    hour_copy = _queue_copy(hour_queue)

    _prune_queue(minute_copy, now_ts, _MINUTE_WINDOW_SECONDS)
    _prune_queue(hour_copy, now_ts, _HOUR_WINDOW_SECONDS)

    tier_key = _normalize_tier(str(entry.get("tier") or fallback_tier or "free"))
    tier_limits = limits.get(tier_key, limits["free"])

    minute_count = int(len(minute_copy))
    hour_count = int(len(hour_copy))

    per_minute = int(tier_limits["perMinute"])
    per_hour = int(tier_limits["perHour"])

    minute_utilization = (float(minute_count) / float(per_minute)) * 100.0 if per_minute > 0 else 0.0
    hour_utilization = (float(hour_count) / float(per_hour)) * 100.0 if per_hour > 0 else 0.0

    last_request_raw = entry.get("lastRequest")
    if isinstance(last_request_raw, dict):
        timestamp = float(last_request_raw.get("timestamp") or 0.0)
        last_request = {
            "path": str(last_request_raw.get("path") or "/"),
            "method": str(last_request_raw.get("method") or "GET").upper(),
            "statusCode": int(last_request_raw.get("statusCode") or 0),
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(timestamp)) if timestamp > 0 else None,
        }
    else:
        last_request = None

    return {
        "user": _normalize_username(username),
        "tier": tier_key,
        "requests": {
            "lastMinute": minute_count,
            "lastHour": hour_count,
        },
        "limits": {
            "perMinute": per_minute,
            "perHour": per_hour,
        },
        "remaining": {
            "minute": max(0, per_minute - minute_count),
            "hour": max(0, per_hour - hour_count),
        },
        "utilizationPercent": {
            "minute": round(minute_utilization, 2),
            "hour": round(hour_utilization, 2),
        },
        "lastRequest": last_request,
    }


def get_quota_usage_snapshot(
    username: str,
    *,
    fallback_tier: str = "free",
) -> Dict[str, Any]:
    user_key = _normalize_username(username)

    with _LOCK:
        entry = _USER_USAGE.get(user_key)
        if entry is None:
            entry = {
                "tier": _normalize_tier(fallback_tier),
                "minuteTimestamps": deque(),
                "hourTimestamps": deque(),
                "lastRequest": None,
            }

        snapshot = _build_snapshot(user_key, entry, fallback_tier=fallback_tier)

    return snapshot


def list_quota_usage_snapshots(limit: int = 100) -> List[Dict[str, Any]]:
    safe_limit = max(1, min(5000, int(limit)))

    with _LOCK:
        ordered_records: List[tuple[float, Dict[str, Any]]] = []
        for user_key, entry in _USER_USAGE.items():
            last_request = entry.get("lastRequest") if isinstance(entry, dict) else None
            last_ts = 0.0
            if isinstance(last_request, dict):
                try:
                    last_ts = float(last_request.get("timestamp") or 0.0)
                except (TypeError, ValueError):
                    last_ts = 0.0

            snapshot = _build_snapshot(
                user_key,
                entry,
                fallback_tier=str(entry.get("tier") or "free"),
            )
            ordered_records.append((last_ts, snapshot))

    ordered_records.sort(key=lambda item: item[0], reverse=True)
    return [snapshot for _, snapshot in ordered_records[:safe_limit]]


def reset_usage_for_tests() -> None:
    with _LOCK:
        _USER_USAGE.clear()


__all__ = [
    "record_request",
    "resolve_tier_from_role",
    "get_quota_usage_snapshot",
    "list_quota_usage_snapshots",
    "reset_usage_for_tests",
]
