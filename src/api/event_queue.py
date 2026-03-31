"""Lightweight thread-safe in-memory event queue for broadcasting events.

Used by the API WebSocket endpoint to stream execution/alert events to
connected clients. This is intentionally simple and memory-bounded.
"""
from __future__ import annotations

import threading
from collections import deque
from typing import Any, List

_QUEUE_MAX = 1000
_queue = deque(maxlen=_QUEUE_MAX)
_lock = threading.Lock()


def push_event(ev: Any) -> None:
    try:
        with _lock:
            _queue.append(ev)
    except Exception:
        pass


def pop_events() -> List[Any]:
    """Pop and return all accumulated events (in order).

    Returns an empty list if no events present.
    """
    out = []
    try:
        with _lock:
            while _queue:
                out.append(_queue.popleft())
    except Exception:
        return []
    return out
