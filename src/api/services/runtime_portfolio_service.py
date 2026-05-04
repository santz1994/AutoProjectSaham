"""Runtime portfolio snapshot & bot status resolution helpers.

Extracted from ``frontend_routes.py`` to isolate heavy business logic
(portfolio reconciliation, bot status aggregation) from route orchestration.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from src.utils.datetime_utils import utcnow


# ---------------------------------------------------------------------------
# ISO datetime parsing & uptime formatting
# ---------------------------------------------------------------------------

def parse_iso_datetime(value: Optional[str]) -> Optional[datetime]:
    """Parse ISO-8601 datetime string, handling 'Z' suffix."""
    raw_value = str(value or "").strip()
    if not raw_value:
        return None

    candidate = raw_value
    if candidate.endswith("Z"):
        candidate = candidate[:-1] + "+00:00"

    try:
        parsed = datetime.fromisoformat(candidate)
    except Exception:
        return None

    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def format_runtime_uptime(total_seconds: int) -> str:
    """Format seconds into human-readable uptime (e.g. '2h 15m')."""
    safe_seconds = max(0, int(total_seconds))
    hours = safe_seconds // 3600
    minutes = (safe_seconds % 3600) // 60
    if hours > 0:
        return f"{hours}h {minutes}m"
    return f"{minutes}m"


# ---------------------------------------------------------------------------
# Portfolio snapshot resolution
# ---------------------------------------------------------------------------

async def resolve_runtime_portfolio_snapshot(
    *,
    safe_float_fn: Any,
    detect_market_fn: Any,
    normalize_symbol_fn: Any,
    symbol_name_fn: Any,
    symbol_sector_fn: Any,
    resolve_candle_anchor_fn: Any,
    portfolio_position_cls: Any,
    portfolio_cls: Any,
    paper_broker_cls: Any,
) -> Any:
    """Resolve current portfolio snapshot via PaperBroker reconciliation."""
    starting_cash = float(
        safe_float_fn(os.getenv("PAPER_STARTING_CASH"), default=100_000_000.0)
        or 100_000_000.0
    )

    adapter = paper_broker_cls(starting_cash=starting_cash)
    positions_map: Dict[str, Any] = {}
    cash = starting_cash
    balance = starting_cash

    try:
        adapter.connect()
        snapshot = adapter.reconcile() or {}
        positions_map = snapshot.get("positions") or {}
        cash = float(safe_float_fn(snapshot.get("cash"), default=starting_cash) or starting_cash)
        balance = float(safe_float_fn(snapshot.get("balance"), default=cash) or cash)
    except Exception:
        positions_map = {}
        cash = starting_cash
        balance = starting_cash
    finally:
        try:
            adapter.disconnect()
        except Exception:
            pass

    positions: List[Any] = []
    market_value = 0.0

    for raw_symbol, raw_quantity in positions_map.items():
        market_hint = detect_market_fn(str(raw_symbol))
        symbol = normalize_symbol_fn(str(raw_symbol), market=market_hint)
        quantity = int(safe_float_fn(raw_quantity, default=0.0) or 0.0)
        if quantity <= 0:
            continue

        anchor = await resolve_candle_anchor_fn(symbol, timeframe="1d")
        current_price = float((anchor or {}).get("price") or 0.0)
        entry_price = current_price
        total_value = float(quantity * current_price)
        market_value += total_value

        positions.append(
            portfolio_position_cls(
                symbol=symbol,
                name=symbol_name_fn(symbol),
                quantity=quantity,
                entryPrice=entry_price,
                currentPrice=current_price,
                totalValue=total_value,
                p_l=0.0,
                percentP_L=0.0,
                sector=symbol_sector_fn(symbol),
                riskScore="Moderate",
            )
        )

    total_value = float(safe_float_fn(balance, default=(cash + market_value)) or (cash + market_value))
    total_p_l = float(total_value - starting_cash)
    percent_p_l = float((total_p_l / starting_cash) * 100.0) if starting_cash > 0 else 0.0

    return portfolio_cls(
        totalValue=round(total_value, 2),
        totalP_L=round(total_p_l, 2),
        percentP_L=round(percent_p_l, 4),
        cash=round(cash, 2),
        purchasingPower=round(cash, 2),
        lastUpdate=utcnow().isoformat(),
        positions=positions,
    )


# ---------------------------------------------------------------------------
# Bot status resolution
# ---------------------------------------------------------------------------

def resolve_runtime_bot_status(
    *,
    state_store: Any,
    default_user_settings: Dict[str, Any],
    default_broker_connection: Dict[str, Any],
    default_system_control: Dict[str, Any],
    bot_status_cls: Any,
    safe_float_fn: Any,
) -> Any:
    """Resolve current bot status from state store logs & settings."""
    logs = state_store.list_ai_logs(limit=250)
    settings = state_store.get_user_settings(default_user_settings)
    broker = state_store.get_broker_connection(default_broker_connection)
    system_control = state_store.get_system_control(default_system_control)
    kill_switch_active = bool(system_control.get("killSwitchActive"))
    kill_switch_reason = str(system_control.get("reason") or "").strip() or None

    trade_like_events = {
        "trade_execution",
        "trade_reconcile",
        "strategy_deploy",
        "strategy_backtest",
    }

    now = utcnow()
    parsed_timestamps = [
        parse_iso_datetime(item.get("timestamp"))
        for item in logs
    ]
    parsed_timestamps = [item for item in parsed_timestamps if item is not None]

    earliest = min(parsed_timestamps) if parsed_timestamps else None
    uptime = format_runtime_uptime(int((now - earliest).total_seconds())) if earliest else None

    today = now.date()
    total_trades_today = 0
    successful_trades = 0
    failed_trades = 0
    last_trade_time = None

    for item in logs:
        event_type = str(item.get("eventType") or "").strip().lower()
        level = str(item.get("level") or "").strip().lower()
        timestamp = parse_iso_datetime(item.get("timestamp"))

        is_trade_like = event_type in trade_like_events or event_type.startswith("trade")
        if not is_trade_like:
            continue

        if timestamp and timestamp.date() == today:
            total_trades_today += 1
            if level == "error":
                failed_trades += 1
            elif level in {"info", "success"}:
                successful_trades += 1

        if timestamp and (last_trade_time is None or timestamp > last_trade_time):
            last_trade_time = timestamp

    resolved_total = successful_trades + failed_trades
    win_rate = float(successful_trades / resolved_total) if resolved_total > 0 else 0.0

    refresh_seconds = int(
        safe_float_fn(settings.get("aiMonitorRefreshSeconds"), default=20.0) or 20.0
    )
    refresh_seconds = max(5, min(refresh_seconds, 300))

    if kill_switch_active:
        resolved_status = "stopped"
        next_analysis = "halted"
    else:
        resolved_status = "running" if bool(broker.get("connected")) else "standby"
        next_analysis = f"{refresh_seconds}s"

    return bot_status_cls(
        status=resolved_status,
        uptime=uptime,
        activeTrades=0,
        totalTradesToday=total_trades_today,
        successfulTrades=successful_trades,
        failedTrades=failed_trades,
        winRate=round(win_rate, 4),
        lastTradeTime=last_trade_time.isoformat() if last_trade_time else None,
        nextAnalysisIn=next_analysis,
        killSwitchActive=kill_switch_active,
        killSwitchReason=kill_switch_reason,
        performanceToday={"totalP_L": 0.0, "percentP_L": 0.0},
    )