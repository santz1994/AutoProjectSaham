"""Runtime control helpers for scheduler, execution, queue, and kill-switch actions."""

from __future__ import annotations

import asyncio
import os
from typing import Any, Callable, Dict, Optional


def runtime_scheduler_status() -> Dict[str, Any]:
    status: Dict[str, Any] = {
        "available": False,
        "running": False,
    }
    try:
        from src.api import server as api_server

        scheduler = getattr(api_server, "_scheduler", None)
        if scheduler is None:
            return status

        thread = getattr(scheduler, "_thread", None)
        status.update(
            {
                "available": True,
                "running": bool(thread and thread.is_alive()),
            }
        )
    except Exception as exc:
        status["error"] = str(exc)

    return status


def runtime_execution_status() -> Dict[str, Any]:
    status: Dict[str, Any] = {
        "available": False,
        "pendingOrders": 0,
        "startupSync": {
            "required": False,
            "completed": True,
            "status": "not_required",
        },
    }
    try:
        from src.api import server as api_server

        execution_manager = getattr(api_server, "_execution_manager", None)
        if execution_manager is None:
            return status

        pending_orders = []
        if hasattr(execution_manager, "get_pending_orders"):
            pending_orders = list(execution_manager.get_pending_orders() or [])

        startup_sync_status = status.get("startupSync")
        if hasattr(execution_manager, "get_startup_sync_status"):
            candidate = execution_manager.get_startup_sync_status()
            if isinstance(candidate, dict):
                startup_sync_status = {
                    **(startup_sync_status or {}),
                    **candidate,
                }

        status.update(
            {
                "available": True,
                "pendingOrders": len(pending_orders),
                "startupSync": startup_sync_status,
            }
        )
    except Exception as exc:
        status["error"] = str(exc)

    return status


def runtime_execution_manager() -> Optional[Any]:
    try:
        from src.api import server as api_server

        return getattr(api_server, "_execution_manager", None)
    except Exception:
        return None


def resolve_live_broker_adapter(provider: str):
    normalized = str(provider or "").strip().lower()

    if normalized == "indopremier":
        from src.brokers.indopremier import IndoPremierBroker

        return IndoPremierBroker
    if normalized == "stockbit":
        from src.brokers.stockbit import StockbitBroker

        return StockbitBroker
    if normalized == "ajaib":
        from src.brokers.ajaib import AjaibBroker

        return AjaibBroker

    return None


def cancel_live_broker_open_orders(
    *,
    state_store: Any,
    default_broker_connection: Dict[str, Any],
    resolve_live_broker_adapter_fn: Callable[[str], Any],
    limit: int = 200,
) -> Dict[str, Any]:
    """Best-effort cancel for open orders on live broker connection."""
    safe_limit = max(1, min(1000, int(limit)))
    summary: Dict[str, Any] = {
        "requested": False,
        "connected": False,
        "provider": None,
        "status": "skipped",
        "openOrders": 0,
        "cancelled": 0,
        "failed": 0,
        "error": None,
    }

    connection = state_store.get_broker_connection(default_broker_connection)
    if not bool(connection.get("connected")):
        summary["status"] = "skipped_not_connected"
        return summary

    trading_mode = str(connection.get("tradingMode") or "paper").strip().lower()
    if trading_mode != "live":
        summary["status"] = "skipped_not_live"
        return summary

    provider = str(connection.get("provider") or "").strip().lower()
    summary["provider"] = provider or None

    adapter_cls = resolve_live_broker_adapter_fn(provider)
    if adapter_cls is None:
        summary["status"] = "unsupported_provider"
        return summary

    credentials = state_store.get_broker_credentials()
    account_id = str(
        connection.get("accountId")
        or credentials.get("accountId")
        or ""
    ).strip()
    api_key = str(credentials.get("apiKey") or "").strip()
    api_secret = str(credentials.get("apiSecret") or "").strip()

    if not account_id or not api_key or not api_secret:
        summary["status"] = "missing_credentials"
        return summary

    summary["requested"] = True

    async def _cancel_async() -> Dict[str, Any]:
        broker = adapter_cls(
            api_key=api_key,
            api_secret=api_secret,
            account_id=account_id,
        )

        try:
            connected = await broker.connect()
            summary["connected"] = bool(connected)
            if not connected:
                summary["status"] = "connect_failed"
                return summary

            cancel_report = await broker.cancel_all_open_orders(limit=safe_limit)
            summary["status"] = str(cancel_report.get("status") or "ok")
            summary["openOrders"] = int(cancel_report.get("openOrders") or 0)
            summary["cancelled"] = int(cancel_report.get("cancelled") or 0)
            summary["failed"] = int(cancel_report.get("failed") or 0)
            summary["error"] = cancel_report.get("error")
            return summary
        except Exception as exc:
            summary["status"] = "error"
            summary["error"] = str(exc)
            return summary
        finally:
            try:
                await broker.disconnect()
            except Exception:
                pass

    try:
        return asyncio.run(_cancel_async())
    except RuntimeError:
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(_cancel_async())
        finally:
            loop.close()


def suspend_runtime_services(
    *,
    cancel_live_broker_open_orders_fn: Callable[[int], Dict[str, Any]],
) -> Dict[str, Any]:
    """Best-effort stop for local scheduler after kill switch activation."""
    actions: Dict[str, Any] = {
        "schedulerStopRequested": False,
        "schedulerWasRunning": False,
        "schedulerStopped": False,
        "pendingOrderCancelRequested": False,
        "pendingOrdersBefore": 0,
        "pendingOrdersCancelled": 0,
        "pendingOrdersAfter": 0,
        "brokerOpenOrderCancelRequested": False,
        "brokerOpenOrdersFound": 0,
        "brokerOpenOrdersCancelled": 0,
        "brokerOpenOrdersFailed": 0,
        "brokerOpenOrderCancelSummary": None,
        "errors": [],
    }

    try:
        from src.api import server as api_server

        scheduler = getattr(api_server, "_scheduler", None)
        if scheduler is not None:
            actions["schedulerStopRequested"] = True
            thread = getattr(scheduler, "_thread", None)
            was_running = bool(thread and thread.is_alive())
            actions["schedulerWasRunning"] = was_running

            if was_running:
                scheduler.stop(timeout=2.0)
                thread_after = getattr(scheduler, "_thread", None)
                actions["schedulerStopped"] = not bool(thread_after and thread_after.is_alive())
            else:
                actions["schedulerStopped"] = True
        else:
            actions["schedulerStopped"] = True

        execution_manager = getattr(api_server, "_execution_manager", None)
        if execution_manager is not None:
            actions["pendingOrderCancelRequested"] = True

            try:
                pending_before = list(execution_manager.get_pending_orders() or [])
            except Exception:
                pending_before = []

            actions["pendingOrdersBefore"] = len(pending_before)

            try:
                if hasattr(execution_manager, "cancel_all_pending_orders"):
                    cancelled = execution_manager.cancel_all_pending_orders(
                        reason="kill_switch"
                    )
                else:
                    cancelled = 0
            except Exception as exc:
                cancelled = 0
                actions["errors"].append(str(exc))

            actions["pendingOrdersCancelled"] = int(cancelled or 0)

            try:
                pending_after = list(execution_manager.get_pending_orders() or [])
            except Exception:
                pending_after = []
            actions["pendingOrdersAfter"] = len(pending_after)

        broker_cancel_summary = cancel_live_broker_open_orders_fn(200)
        actions["brokerOpenOrderCancelRequested"] = bool(
            broker_cancel_summary.get("requested")
        )
        actions["brokerOpenOrdersFound"] = int(
            broker_cancel_summary.get("openOrders") or 0
        )
        actions["brokerOpenOrdersCancelled"] = int(
            broker_cancel_summary.get("cancelled") or 0
        )
        actions["brokerOpenOrdersFailed"] = int(
            broker_cancel_summary.get("failed") or 0
        )
        actions["brokerOpenOrderCancelSummary"] = broker_cancel_summary
        if broker_cancel_summary.get("error"):
            actions["errors"].append(str(broker_cancel_summary["error"]))
    except Exception as exc:
        actions["errors"].append(str(exc))

    return actions


def celery_queue_backlog_snapshot() -> Dict[str, Any]:
    enabled = str(os.getenv("AUTOSAHAM_USE_CELERY", "")).strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    if not enabled:
        return {
            "enabled": False,
            "available": False,
            "connectedWorkers": [],
            "reservedCount": 0,
            "scheduledCount": 0,
            "activeCount": 0,
            "backlogEstimate": 0,
        }

    try:
        from src.tasks import app as celery_app

        inspector = celery_app.control.inspect(timeout=0.75)
        reserved = inspector.reserved() or {}
        scheduled = inspector.scheduled() or {}
        active = inspector.active() or {}

        workers = sorted(set(reserved.keys()) | set(scheduled.keys()) | set(active.keys()))
        reserved_count = sum(len(items or []) for items in reserved.values())
        scheduled_count = sum(len(items or []) for items in scheduled.values())
        active_count = sum(len(items or []) for items in active.values())

        return {
            "enabled": True,
            "available": True,
            "connectedWorkers": workers,
            "reservedCount": int(reserved_count),
            "scheduledCount": int(scheduled_count),
            "activeCount": int(active_count),
            "backlogEstimate": int(reserved_count + scheduled_count),
        }
    except Exception as exc:
        return {
            "enabled": True,
            "available": False,
            "connectedWorkers": [],
            "reservedCount": 0,
            "scheduledCount": 0,
            "activeCount": 0,
            "backlogEstimate": 0,
            "error": str(exc),
        }


def ws_backplane_health_snapshot() -> Dict[str, Any]:
    try:
        from src.api.event_queue import get_backplane_health

        return get_backplane_health()
    except Exception as exc:
        return {
            "instanceId": None,
            "queueDepth": 0,
            "queueCapacity": 0,
            "seenEventCacheSize": 0,
            "seenEventCacheCapacity": 0,
            "backplane": {
                "enabled": False,
                "channel": None,
                "redisUrlConfigured": False,
                "redisConnected": False,
                "subscriberReady": False,
                "initAttempted": False,
                "lastError": str(exc),
                "lastErrorAt": None,
            },
        }


def last_state_migration_timestamp(
    *,
    state_store: Any,
    limit: int = 200,
) -> Optional[str]:
    try:
        logs = state_store.list_ai_logs(limit=limit)
    except Exception:
        return None

    for item in logs:
        if str(item.get("eventType") or "").strip().lower() != "state_store_migration":
            continue
        candidate = str(item.get("timestamp") or "").strip()
        if candidate:
            return candidate
    return None
