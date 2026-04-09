from __future__ import annotations

import asyncio

from src.api import frontend_routes


async def _run_immediate(func, *args, **kwargs):
    return func(*args, **kwargs)


def test_get_migration_control_center_includes_operational_sections(monkeypatch):
    monkeypatch.setattr(frontend_routes, "_run_blocking", _run_immediate)
    monkeypatch.setattr(
        frontend_routes._state_store,
        "get_state_migration_status",
        lambda: {
            "secureState": {"sqliteCount": 3, "redisCachedCount": 2},
            "aiLogs": {"sqliteCount": 10, "postgresCount": 8},
        },
    )
    monkeypatch.setattr(
        frontend_routes._state_store,
        "get_broker_connection",
        lambda defaults: {"connected": True, "provider": "indopremier"},
    )
    monkeypatch.setattr(
        frontend_routes,
        "_kill_switch_state",
        lambda: {"killSwitchActive": True, "reason": "panic"},
    )
    monkeypatch.setattr(
        frontend_routes,
        "_ws_backplane_health_snapshot",
        lambda: {
            "queueDepth": 4,
            "queueCapacity": 1000,
            "seenEventCacheSize": 12,
            "seenEventCacheCapacity": 5000,
            "backplane": {"enabled": True, "redisConnected": True},
        },
    )
    monkeypatch.setattr(
        frontend_routes,
        "_celery_queue_backlog_snapshot",
        lambda: {
            "enabled": True,
            "available": True,
            "reservedCount": 2,
            "scheduledCount": 3,
            "activeCount": 1,
            "backlogEstimate": 5,
            "connectedWorkers": ["worker@node-a"],
        },
    )
    monkeypatch.setattr(
        frontend_routes,
        "_runtime_scheduler_status",
        lambda: {"available": True, "running": False},
    )
    monkeypatch.setattr(
        frontend_routes,
        "_last_state_migration_timestamp",
        lambda limit=200: "2026-04-09T12:00:00",
    )

    payload = asyncio.run(frontend_routes.get_migration_control_center())

    assert payload["status"] == "ok"
    assert payload["killSwitch"]["killSwitchActive"] is True
    assert payload["queueBacklog"]["websocket"]["depth"] == 4
    assert payload["queueBacklog"]["celery"]["backlogEstimate"] == 5
    assert payload["runtime"]["scheduler"]["available"] is True
    assert payload["stateStore"]["secureState"]["sqliteCount"] == 3


def test_activate_kill_switch_returns_runtime_actions(monkeypatch):
    monkeypatch.setattr(frontend_routes, "_run_blocking", _run_immediate)
    monkeypatch.setattr(
        frontend_routes,
        "_kill_switch_state",
        lambda: {
            "killSwitchActive": False,
            "reason": None,
            "activatedBy": None,
            "activatedAt": None,
        },
    )
    monkeypatch.setattr(
        frontend_routes,
        "_suspend_runtime_services",
        lambda: {
            "schedulerStopRequested": True,
            "schedulerWasRunning": True,
            "schedulerStopped": True,
            "errors": [],
        },
    )
    monkeypatch.setattr(
        frontend_routes._state_store,
        "set_system_control",
        lambda payload: payload,
    )
    monkeypatch.setattr(
        frontend_routes._state_store,
        "append_ai_log",
        lambda **kwargs: None,
    )
    monkeypatch.setattr(frontend_routes, "_emit_kill_switch_event", lambda *args, **kwargs: None)

    response = asyncio.run(
        frontend_routes.activate_kill_switch(
            frontend_routes.KillSwitchPayload(reason="panic test", actor="unit-test")
        )
    )

    assert response["status"] == "activated"
    assert response["killSwitch"]["killSwitchActive"] is True
    assert response["runtimeActions"]["schedulerStopped"] is True
