from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

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
        "_runtime_execution_status",
        lambda: {"available": True, "pendingOrders": 2},
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
    assert payload["runtime"]["execution"]["pendingOrders"] == 2
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
            request=SimpleNamespace(cookies={}),
            payload=frontend_routes.KillSwitchPayload(reason="panic test", actor="unit-test"),
        )
    )

    assert response["status"] == "activated"
    assert response["killSwitch"]["killSwitchActive"] is True
    assert response["runtimeActions"]["schedulerStopped"] is True


def test_suspend_runtime_services_cancels_pending_orders(monkeypatch):
    from src.api import server as api_server

    class _FakeExecutionManager:
        def __init__(self):
            self._orders = [{"order_id": "a"}, {"order_id": "b"}]
            self.last_reason = None

        def get_pending_orders(self):
            return list(self._orders)

        def cancel_all_pending_orders(self, reason: str = "manual"):
            self.last_reason = reason
            cancelled = len(self._orders)
            self._orders = []
            return cancelled

    fake_manager = _FakeExecutionManager()
    monkeypatch.setattr(api_server, "_scheduler", None, raising=False)
    monkeypatch.setattr(api_server, "_execution_manager", fake_manager, raising=False)
    monkeypatch.setattr(
        frontend_routes,
        "_cancel_live_broker_open_orders",
        lambda limit=200: {
            "requested": False,
            "status": "skipped_not_connected",
            "openOrders": 0,
            "cancelled": 0,
            "failed": 0,
            "error": None,
        },
    )

    actions = frontend_routes._suspend_runtime_services()

    assert actions["schedulerStopped"] is True
    assert actions["pendingOrderCancelRequested"] is True
    assert actions["pendingOrdersBefore"] == 2
    assert actions["pendingOrdersCancelled"] == 2
    assert actions["pendingOrdersAfter"] == 0
    assert actions["brokerOpenOrderCancelRequested"] is False
    assert actions["brokerOpenOrdersCancelled"] == 0
    assert fake_manager.last_reason == "kill_switch"


def test_suspend_runtime_services_includes_live_broker_cancel_summary(monkeypatch):
    from src.api import server as api_server

    monkeypatch.setattr(api_server, "_scheduler", None, raising=False)
    monkeypatch.setattr(api_server, "_execution_manager", None, raising=False)
    monkeypatch.setattr(
        frontend_routes,
        "_cancel_live_broker_open_orders",
        lambda limit=200: {
            "requested": True,
            "provider": "indopremier",
            "status": "ok",
            "openOrders": 3,
            "cancelled": 2,
            "failed": 1,
            "error": None,
        },
    )

    actions = frontend_routes._suspend_runtime_services()

    assert actions["brokerOpenOrderCancelRequested"] is True
    assert actions["brokerOpenOrdersFound"] == 3
    assert actions["brokerOpenOrdersCancelled"] == 2
    assert actions["brokerOpenOrdersFailed"] == 1


def test_cancel_live_broker_open_orders_skips_non_live(monkeypatch):
    monkeypatch.setattr(
        frontend_routes._state_store,
        "get_broker_connection",
        lambda defaults: {
            "connected": True,
            "provider": "indopremier",
            "tradingMode": "paper",
            "accountId": "ACC-1",
        },
    )

    summary = frontend_routes._cancel_live_broker_open_orders(limit=50)

    assert summary["requested"] is False
    assert summary["status"] == "skipped_not_live"


def test_cancel_live_broker_open_orders_unsupported_provider(monkeypatch):
    monkeypatch.setattr(
        frontend_routes._state_store,
        "get_broker_connection",
        lambda defaults: {
            "connected": True,
            "provider": "indonesia-securities",
            "tradingMode": "live",
            "accountId": "ACC-1",
        },
    )
    monkeypatch.setattr(
        frontend_routes._state_store,
        "get_broker_credentials",
        lambda defaults=None: {
            "provider": "indonesia-securities",
            "accountId": "ACC-1",
            "apiKey": "k",
            "apiSecret": "s",
        },
    )

    summary = frontend_routes._cancel_live_broker_open_orders(limit=50)

    assert summary["requested"] is False
    assert summary["status"] == "unsupported_provider"


def test_get_execution_pending_orders_snapshot(monkeypatch):
    from src.api import server as api_server

    class _FakeExecutionManager:
        def get_pending_orders(self):
            return [
                {"order_id": "lim-1", "symbol": "BBCA.JK", "side": "buy"},
                {"order_id": "lim-2", "symbol": "BMRI.JK", "side": "sell"},
            ]

    monkeypatch.setattr(frontend_routes, "_run_blocking", _run_immediate)
    monkeypatch.setattr(
        frontend_routes,
        "_runtime_execution_status",
        lambda: {"available": True, "pendingOrders": 2},
    )
    monkeypatch.setattr(
        api_server,
        "_execution_manager",
        _FakeExecutionManager(),
        raising=False,
    )

    payload = asyncio.run(frontend_routes.get_execution_pending_orders(limit=1))

    assert payload["status"] == "ok"
    assert payload["execution"]["available"] is True
    assert payload["total"] == 2
    assert len(payload["pendingOrders"]) == 1


def test_authorize_kill_switch_actor_requires_authenticated_admin(monkeypatch):
    monkeypatch.setenv("AUTOSAHAM_KILL_SWITCH_REQUIRE_ADMIN", "true")

    with pytest.raises(HTTPException) as exc:
        frontend_routes._authorize_kill_switch_actor(
            None,
            frontend_routes.KillSwitchPayload(reason="panic", actor="ops"),
        )

    assert exc.value.status_code == 401


def test_authorize_kill_switch_actor_rejects_non_admin_user(monkeypatch):
    monkeypatch.setenv("AUTOSAHAM_KILL_SWITCH_REQUIRE_ADMIN", "true")
    monkeypatch.setenv("AUTOSAHAM_KILL_SWITCH_ADMIN_USERS", "admin,ops-admin")
    monkeypatch.setattr(frontend_routes, "get_user_from_token", lambda token: "trader")

    with pytest.raises(HTTPException) as exc:
        frontend_routes._authorize_kill_switch_actor(
            SimpleNamespace(cookies={"auth_token": "session-token"}),
            frontend_routes.KillSwitchPayload(reason="panic"),
        )

    assert exc.value.status_code == 403


def test_authorize_kill_switch_actor_accepts_admin_with_fallback_2fa(monkeypatch):
    monkeypatch.setenv("AUTOSAHAM_KILL_SWITCH_REQUIRE_ADMIN", "true")
    monkeypatch.setenv("AUTOSAHAM_KILL_SWITCH_ADMIN_USERS", "admin")
    monkeypatch.setenv("AUTOSAHAM_KILL_SWITCH_REQUIRE_2FA", "true")
    monkeypatch.setenv("AUTOSAHAM_KILL_SWITCH_2FA_CODE", "246810")
    monkeypatch.setattr(frontend_routes, "get_user_from_token", lambda token: "admin")

    actor = frontend_routes._authorize_kill_switch_actor(
        SimpleNamespace(cookies={"auth_token": "session-token"}),
        frontend_routes.KillSwitchPayload(reason="panic", challengeCode="246810"),
    )

    assert actor == "admin"


def test_authorize_kill_switch_actor_rejects_invalid_fallback_2fa(monkeypatch):
    monkeypatch.setenv("AUTOSAHAM_KILL_SWITCH_REQUIRE_ADMIN", "true")
    monkeypatch.setenv("AUTOSAHAM_KILL_SWITCH_ADMIN_USERS", "admin")
    monkeypatch.setenv("AUTOSAHAM_KILL_SWITCH_REQUIRE_2FA", "true")
    monkeypatch.setenv("AUTOSAHAM_KILL_SWITCH_2FA_CODE", "246810")
    monkeypatch.setattr(frontend_routes, "get_user_from_token", lambda token: "admin")

    with pytest.raises(HTTPException) as exc:
        frontend_routes._authorize_kill_switch_actor(
            SimpleNamespace(cookies={"auth_token": "session-token"}),
            frontend_routes.KillSwitchPayload(reason="panic", challengeCode="000000"),
        )

    assert exc.value.status_code == 401


def test_authorize_kill_switch_actor_accepts_legacy_activated_by(monkeypatch):
    monkeypatch.setenv("AUTOSAHAM_KILL_SWITCH_REQUIRE_ADMIN", "false")
    monkeypatch.setenv("AUTOSAHAM_KILL_SWITCH_REQUIRE_2FA", "false")

    actor = frontend_routes._authorize_kill_switch_actor(
        SimpleNamespace(cookies={}),
        frontend_routes.KillSwitchPayload(reason="panic", activatedBy="legacy-ops"),
    )

    assert actor == "legacy-ops"


def test_authorize_kill_switch_actor_enforces_csrf_when_enabled(monkeypatch):
    monkeypatch.setenv("AUTOSAHAM_CSRF_PROTECTION_ENABLED", "true")
    monkeypatch.setenv("AUTOSAHAM_KILL_SWITCH_REQUIRE_ADMIN", "true")
    monkeypatch.setenv("AUTOSAHAM_KILL_SWITCH_ADMIN_USERS", "ops-admin")
    monkeypatch.setattr(
        frontend_routes,
        "get_session_context",
        lambda token: {
            "username": "ops-admin",
            "role": "admin",
            "csrfToken": "csrf-123",
        },
    )

    request = SimpleNamespace(
        cookies={"auth_token": "tok-1", "csrf_token": "csrf-123"},
        headers={},
    )

    with pytest.raises(HTTPException) as exc:
        frontend_routes._authorize_kill_switch_actor(
            request,
            frontend_routes.KillSwitchPayload(reason="panic", actor="ops-admin"),
        )

    assert exc.value.status_code == 403


def test_authorize_kill_switch_actor_accepts_valid_csrf_when_enabled(monkeypatch):
    monkeypatch.setenv("AUTOSAHAM_CSRF_PROTECTION_ENABLED", "true")
    monkeypatch.setenv("AUTOSAHAM_KILL_SWITCH_REQUIRE_ADMIN", "true")
    monkeypatch.setenv("AUTOSAHAM_KILL_SWITCH_ADMIN_USERS", "ops-admin")
    monkeypatch.setattr(
        frontend_routes,
        "get_session_context",
        lambda token: {
            "username": "ops-admin",
            "role": "admin",
            "csrfToken": "csrf-123",
        },
    )

    request = SimpleNamespace(
        cookies={"auth_token": "tok-1", "csrf_token": "csrf-123"},
        headers={"x-csrf-token": "csrf-123"},
    )

    actor = frontend_routes._authorize_kill_switch_actor(
        request,
        frontend_routes.KillSwitchPayload(reason="panic"),
    )

    assert actor == "ops-admin"


def test_require_role_operation_blocks_viewer(monkeypatch):
    monkeypatch.setenv("AUTOSAHAM_ROLE_GUARD_ENABLED", "true")
    monkeypatch.setenv("AUTOSAHAM_CSRF_PROTECTION_ENABLED", "false")
    monkeypatch.setattr(
        frontend_routes,
        "get_session_context",
        lambda token: {
            "username": "viewer-user",
            "role": "viewer",
            "csrfToken": "",
        },
    )

    request = SimpleNamespace(cookies={"auth_token": "tok-1"}, headers={})
    with pytest.raises(HTTPException) as exc:
        frontend_routes._require_role_operation(
            request,
            "Strategy deploy",
            allowed_roles={"trader", "developer"},
        )

    assert exc.value.status_code == 403


def test_require_role_operation_allows_trader(monkeypatch):
    monkeypatch.setenv("AUTOSAHAM_ROLE_GUARD_ENABLED", "true")
    monkeypatch.setenv("AUTOSAHAM_CSRF_PROTECTION_ENABLED", "false")
    monkeypatch.setattr(
        frontend_routes,
        "get_session_context",
        lambda token: {
            "username": "trader-user",
            "role": "trader",
            "csrfToken": "",
        },
    )

    request = SimpleNamespace(cookies={"auth_token": "tok-1"}, headers={})
    context = frontend_routes._require_role_operation(
        request,
        "Strategy deploy",
        allowed_roles={"trader", "developer"},
    )

    assert context["username"] == "trader-user"
    assert context["role"] == "trader"


def test_submit_execution_order_limit_success(monkeypatch):
    class _FakeExecutionManager:
        def place_limit_order(
            self,
            symbol: str,
            side: str,
            qty: int,
            limit_price: float,
            previous_close=None,
        ):
            assert symbol == "BBCA.JK"
            assert side == "buy"
            assert qty == 5
            assert limit_price == 9050.0
            return {
                "status": "pending",
                "order_id": "lim-77",
            }

    monkeypatch.setattr(
        frontend_routes,
        "_require_role_operation",
        lambda *args, **kwargs: {
            "username": "trader-user",
            "role": "trader",
            "csrfToken": "",
        },
    )
    monkeypatch.setattr(
        frontend_routes,
        "_runtime_execution_manager",
        lambda: _FakeExecutionManager(),
    )
    monkeypatch.setattr(
        frontend_routes._state_store,
        "append_ai_log",
        lambda **kwargs: None,
    )

    payload = frontend_routes.ExecutionOrderPayload(
        symbol="bbca.jk",
        side="BUY",
        qty=5,
        orderType="limit",
        limitPrice=9050,
    )

    response = asyncio.run(
        frontend_routes.submit_execution_order(
            payload,
            request=SimpleNamespace(cookies={}, headers={}),
        )
    )

    assert response["status"] == "ok"
    assert response["accepted"] is True
    assert response["orderType"] == "limit"
    assert response["submission"]["order_id"] == "lim-77"


def test_submit_execution_order_market_success(monkeypatch):
    class _FakeExecutionManager:
        def place_order(
            self,
            symbol: str,
            side: str,
            qty: int,
            price: float,
            previous_close=None,
        ):
            assert symbol == "BBCA.JK"
            assert side == "sell"
            assert qty == 3
            assert price == 9100.0
            return {
                "status": "filled",
                "id": "mkt-21",
            }

    monkeypatch.setattr(
        frontend_routes,
        "_require_role_operation",
        lambda *args, **kwargs: {
            "username": "trader-user",
            "role": "trader",
            "csrfToken": "",
        },
    )
    monkeypatch.setattr(
        frontend_routes,
        "_runtime_execution_manager",
        lambda: _FakeExecutionManager(),
    )
    monkeypatch.setattr(
        frontend_routes._state_store,
        "append_ai_log",
        lambda **kwargs: None,
    )

    payload = frontend_routes.ExecutionOrderPayload(
        symbol="bbca.jk",
        side="SELL",
        qty=3,
        orderType="market",
        marketPrice=9100,
    )

    response = asyncio.run(
        frontend_routes.submit_execution_order(
            payload,
            request=SimpleNamespace(cookies={}, headers={}),
        )
    )

    assert response["status"] == "ok"
    assert response["accepted"] is True
    assert response["orderType"] == "market"
    assert response["submission"]["status"] == "filled"


def test_submit_execution_order_requires_manager(monkeypatch):
    monkeypatch.setattr(
        frontend_routes,
        "_require_role_operation",
        lambda *args, **kwargs: {
            "username": "trader-user",
            "role": "trader",
            "csrfToken": "",
        },
    )
    monkeypatch.setattr(frontend_routes, "_runtime_execution_manager", lambda: None)

    payload = frontend_routes.ExecutionOrderPayload(
        symbol="BBCA.JK",
        side="BUY",
        qty=1,
        orderType="limit",
        limitPrice=9000,
    )

    with pytest.raises(HTTPException) as exc:
        asyncio.run(
            frontend_routes.submit_execution_order(
                payload,
                request=SimpleNamespace(cookies={}, headers={}),
            )
        )

    assert exc.value.status_code == 503
