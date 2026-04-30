import time

from src.api.event_queue import get_backplane_health, pop_events, push_event


def _drain_events():
    # Best-effort queue drain to isolate test assertions.
    for _ in range(3):
        _ = pop_events()


def test_push_pop_strips_internal_metadata():
    _drain_events()

    push_event({"type": "tick", "symbol": "BTCUSDT", "price": 100.0})
    events = pop_events()

    assert isinstance(events, list)
    assert events
    payload = events[-1]
    assert payload["type"] == "tick"
    assert payload["symbol"] == "BTCUSDT"
    assert "__eventId" not in payload
    assert "__origin" not in payload
    assert "__ts" not in payload


def test_push_event_deduplicates_same_event_id():
    _drain_events()
    event_id = f"unit-{time.time_ns()}"

    push_event({"type": "unit_test", "value": 1, "__eventId": event_id})
    push_event({"type": "unit_test", "value": 1, "__eventId": event_id})

    events = pop_events()
    matched = [item for item in events if item.get("type") == "unit_test" and item.get("value") == 1]

    assert len(matched) == 1


def test_backplane_health_snapshot_shape():
    _drain_events()
    push_event({"type": "health_probe", "value": 1})

    payload = get_backplane_health()

    assert isinstance(payload, dict)
    assert "queueDepth" in payload
    assert "queueCapacity" in payload
    assert "backplane" in payload
    assert isinstance(payload["backplane"], dict)
    assert "enabled" in payload["backplane"]
    assert "redisConnected" in payload["backplane"]
