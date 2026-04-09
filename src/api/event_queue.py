"""Thread-safe event queue with optional Redis Pub/Sub backplane.

When `AUTOSAHAM_WS_BACKPLANE_ENABLED=1`, each pushed event is also published
to Redis so other API instances can consume and broadcast to their websocket
clients. The queue remains memory-bounded and gracefully degrades to local-only
mode when Redis is unavailable.
"""
from __future__ import annotations

import json
import os
import threading
import time
import uuid
from collections import deque
from typing import Any, Dict, List, Optional


_QUEUE_MAX = 1000
_SEEN_EVENT_MAX = 5000
_BACKPLANE_POLL_MAX = 200
_DEFAULT_CHANNEL = "autosaham:events"

_queue = deque(maxlen=_QUEUE_MAX)
_seen_event_ids = deque()
_seen_event_lookup: set[str] = set()
_lock = threading.Lock()

_instance_id = os.getenv("AUTOSAHAM_INSTANCE_ID", "").strip() or f"api-{uuid.uuid4().hex[:8]}"
_backplane_channel = str(
    os.getenv("AUTOSAHAM_WS_BACKPLANE_CHANNEL", _DEFAULT_CHANNEL)
).strip() or _DEFAULT_CHANNEL

_redis_init_attempted = False
_redis_client = None
_redis_pubsub = None


def _env_flag(name: str, default: bool = False) -> bool:
    value = str(os.getenv(name, "")).strip().lower()
    if not value:
        return default
    return value in {"1", "true", "yes", "on"}


def _backplane_enabled() -> bool:
    return _env_flag("AUTOSAHAM_WS_BACKPLANE_ENABLED", False)


def _resolve_redis_url() -> str:
    candidates = [
        os.getenv("AUTOSAHAM_STATE_REDIS_URL"),
        os.getenv("REDIS_URL"),
        os.getenv("CELERY_BROKER_URL"),
    ]
    for item in candidates:
        candidate = str(item or "").strip()
        if candidate.lower().startswith(("redis://", "rediss://")):
            return candidate
    return ""


def _init_backplane() -> None:
    global _redis_init_attempted
    global _redis_client
    global _redis_pubsub

    if _redis_init_attempted:
        return

    _redis_init_attempted = True
    if not _backplane_enabled():
        return

    redis_url = _resolve_redis_url()
    if not redis_url:
        return

    try:
        import redis  # type: ignore

        client = redis.Redis.from_url(
            redis_url,
            decode_responses=True,
            socket_connect_timeout=0.5,
            socket_timeout=0.5,
        )
        client.ping()
        pubsub = client.pubsub(ignore_subscribe_messages=True)
        pubsub.subscribe(_backplane_channel)
        _redis_client = client
        _redis_pubsub = pubsub
    except Exception:
        _redis_client = None
        _redis_pubsub = None


def _normalize_event(ev: Any) -> Dict[str, Any]:
    if isinstance(ev, dict):
        payload = dict(ev)
    else:
        payload = {"type": "event", "payload": ev}

    payload.setdefault("type", "event")
    payload["__eventId"] = str(payload.get("__eventId") or uuid.uuid4().hex)
    payload["__origin"] = str(payload.get("__origin") or _instance_id)
    payload["__ts"] = float(payload.get("__ts") or time.time())
    return payload


def _strip_internal_fields(ev: Dict[str, Any]) -> Dict[str, Any]:
    return {
        key: value
        for key, value in ev.items()
        if not str(key).startswith("__")
    }


def _mark_seen(event_id: str) -> None:
    if not event_id:
        return

    if event_id in _seen_event_lookup:
        return

    while len(_seen_event_ids) >= _SEEN_EVENT_MAX:
        stale = _seen_event_ids.popleft()
        _seen_event_lookup.discard(stale)

    _seen_event_ids.append(event_id)
    _seen_event_lookup.add(event_id)


def _is_seen(event_id: str) -> bool:
    if not event_id:
        return False
    return event_id in _seen_event_lookup


def _publish_backplane(ev: Dict[str, Any]) -> None:
    _init_backplane()
    if _redis_client is None:
        return

    try:
        _redis_client.publish(
            _backplane_channel,
            json.dumps(ev, separators=(",", ":"), ensure_ascii=True),
        )
    except Exception:
        pass


def _pull_backplane_events() -> List[Dict[str, Any]]:
    _init_backplane()
    if _redis_pubsub is None:
        return []

    incoming: List[Dict[str, Any]] = []
    try:
        for _ in range(_BACKPLANE_POLL_MAX):
            message = _redis_pubsub.get_message(timeout=0.0)
            if not message:
                break

            raw = message.get("data")
            if not raw:
                continue

            try:
                payload = json.loads(str(raw))
            except Exception:
                continue

            if not isinstance(payload, dict):
                continue

            event_id = str(payload.get("__eventId") or "")
            if _is_seen(event_id):
                continue

            _mark_seen(event_id)
            incoming.append(payload)
    except Exception:
        return []

    return incoming


def push_event(ev: Any) -> None:
    payload = _normalize_event(ev)
    event_id = str(payload.get("__eventId") or "")

    try:
        with _lock:
            if event_id and _is_seen(event_id):
                return

            _mark_seen(event_id)
            _queue.append(payload)
    except Exception:
        return

    _publish_backplane(payload)


def pop_events() -> List[Any]:
    """Pop and return all accumulated events in FIFO order."""
    try:
        backplane_events = _pull_backplane_events()
        if backplane_events:
            with _lock:
                for payload in backplane_events:
                    _queue.append(payload)

        out: List[Any] = []
        with _lock:
            while _queue:
                payload = _queue.popleft()
                if isinstance(payload, dict):
                    out.append(_strip_internal_fields(payload))
                else:
                    out.append(payload)
        return out
    except Exception:
        return []
