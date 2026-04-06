"""Vector-style backtester for signal-based strategies.

Simple sequential simulator that supports slippage and commission and
returns common performance metrics and an equity curve.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import pandas as pd


@dataclass
class LiveBacktestConstraints:
    """Runtime constraints to approximate live execution guardrails."""

    max_exposure_pct: Optional[float] = None
    max_position_units: Optional[int] = None
    max_drawdown_pct: Optional[float] = None
    trade_cooldown_bars: int = 0
    max_total_trades: Optional[int] = None
    flatten_on_risk_stop: bool = True


def _resolve_constraints(
    constraints: Optional[LiveBacktestConstraints | Dict[str, Any]],
) -> LiveBacktestConstraints:
    if constraints is None:
        return LiveBacktestConstraints()
    if isinstance(constraints, LiveBacktestConstraints):
        return constraints
    if isinstance(constraints, dict):
        allowed = {
            "max_exposure_pct",
            "max_position_units",
            "max_drawdown_pct",
            "trade_cooldown_bars",
            "max_total_trades",
            "flatten_on_risk_stop",
        }
        values = {k: v for k, v in constraints.items() if k in allowed}
        return LiveBacktestConstraints(**values)
    raise TypeError("constraints must be None, dict, or LiveBacktestConstraints")


def backtest_signals(
    prices: List[float],
    signals: List[int],
    initial_cash: float = 10000.0,
    commission_pct: float = 0.0005,
    slippage_pct: float = 0.0005,
    position_size: int = 1,
    constraints: Optional[LiveBacktestConstraints | Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Run a simple backtest.

    prices: chronological list of prices
    signals: same-length list with values 1 (buy), -1 (sell), 0 (hold)
    position_size: integer units to buy on each buy signal
    """
    if len(prices) != len(signals):
        raise ValueError("prices and signals must have the same length")

    s = pd.Series(prices)
    sig = pd.Series(signals).fillna(0).astype(int)
    cfg = _resolve_constraints(constraints)

    cash = float(initial_cash)
    pos = 0
    trades = []
    equity = []
    constraint_events = []
    last_trade_t: Optional[int] = None
    peak_equity = float(initial_cash)
    risk_stop_triggered = False

    def _execute_sell(t_idx: int, px: float, reason: str = "sell") -> None:
        nonlocal cash, pos, last_trade_t
        qty = int(pos)
        if qty <= 0:
            return
        exec_price = px * (1.0 - slippage_pct)
        commission = exec_price * qty * commission_pct
        proceeds = exec_price * qty - commission
        cash += proceeds
        trades.append(
            {
                "t": t_idx,
                "side": reason,
                "qty": qty,
                "price": exec_price,
                "commission": commission,
            }
        )
        pos = 0
        last_trade_t = t_idx

    for t in range(len(s)):
        price = float(s.iloc[t])
        action = int(sig.iloc[t])
        equity_now = cash + pos * price
        peak_equity = max(peak_equity, equity_now)

        if (
            cfg.max_drawdown_pct is not None
            and peak_equity > 0
            and (equity_now - peak_equity) / peak_equity <= -abs(float(cfg.max_drawdown_pct))
        ):
            if not risk_stop_triggered:
                risk_stop_triggered = True
                constraint_events.append(
                    {
                        "t": t,
                        "type": "risk_stop",
                        "drawdown": float((equity_now - peak_equity) / peak_equity),
                    }
                )

            if cfg.flatten_on_risk_stop and pos > 0:
                _execute_sell(t, price, reason="sell_risk")

        if risk_stop_triggered:
            equity.append(cash + pos * price)
            continue

        if action == 1:
            if cfg.max_total_trades is not None and len(trades) >= int(cfg.max_total_trades):
                constraint_events.append(
                    {
                        "t": t,
                        "type": "blocked",
                        "reason": "max_total_trades",
                    }
                )
                equity.append(cash + pos * price)
                continue

            if (
                cfg.trade_cooldown_bars > 0
                and last_trade_t is not None
                and (t - last_trade_t) <= int(cfg.trade_cooldown_bars)
            ):
                constraint_events.append(
                    {
                        "t": t,
                        "type": "blocked",
                        "reason": "cooldown",
                    }
                )
                equity.append(cash + pos * price)
                continue

            qty = int(position_size)

            if cfg.max_position_units is not None:
                qty_cap = max(0, int(cfg.max_position_units) - int(pos))
                qty = min(qty, qty_cap)

            if cfg.max_exposure_pct is not None:
                max_notional = max(0.0, float(cfg.max_exposure_pct) * float(equity_now))
                current_notional = float(pos) * price
                available_notional = max(0.0, max_notional - current_notional)
                per_unit_cost = price * (1.0 + float(slippage_pct) + float(commission_pct))
                exposure_qty = int(available_notional // per_unit_cost) if per_unit_cost > 0 else 0
                qty = min(qty, exposure_qty)

            if qty <= 0:
                constraint_events.append(
                    {
                        "t": t,
                        "type": "blocked",
                        "reason": "position_or_exposure_limit",
                    }
                )
                equity.append(cash + pos * price)
                continue

            exec_price = price * (1.0 + slippage_pct)
            commission = exec_price * qty * commission_pct
            cost = exec_price * qty + commission
            if cost <= cash:
                cash -= cost
                pos += qty
                last_trade_t = t
                trades.append(
                    {
                        "t": t,
                        "side": "buy",
                        "qty": qty,
                        "price": exec_price,
                        "commission": commission,
                    }
                )
            else:
                constraint_events.append(
                    {
                        "t": t,
                        "type": "blocked",
                        "reason": "insufficient_cash",
                    }
                )
        elif action == -1:
            if pos > 0:
                _execute_sell(t, price, reason="sell")

        equity.append(cash + pos * price)

    eq = pd.Series(equity)
    returns = eq.pct_change().fillna(0)

    cum_return = float(eq.iloc[-1] / initial_cash - 1.0)
    returns_std = returns.std()
    sharpe = (
        (returns.mean() / returns_std * math.sqrt(252)) if returns_std > 0 else None
    )

    cummax = eq.cummax()
    drawdown = (eq - cummax) / cummax
    max_dd = float(drawdown.min()) if not drawdown.empty else 0.0

    return {
        "final_balance": float(eq.iloc[-1]) if not eq.empty else float(initial_cash),
        "equity_curve": eq.tolist(),
        "cum_return": cum_return,
        "sharpe": sharpe,
        "max_drawdown": max_dd,
        "trades": trades,
        "risk_stop_triggered": bool(risk_stop_triggered),
        "constraint_events": constraint_events,
    }
