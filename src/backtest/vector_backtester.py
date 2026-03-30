"""Vector-style backtester for signal-based strategies.

Simple sequential simulator that supports slippage and commission and
returns common performance metrics and an equity curve.
"""
from __future__ import annotations

import math
from typing import List, Dict, Any

import numpy as np
import pandas as pd


def backtest_signals(prices: List[float], signals: List[int], initial_cash: float = 10000.0, commission_pct: float = 0.0005, slippage_pct: float = 0.0005, position_size: int = 1) -> Dict[str, Any]:
    """Run a simple backtest.

    prices: chronological list of prices
    signals: same-length list with values 1 (buy), -1 (sell), 0 (hold)
    position_size: integer units to buy on each buy signal
    """
    if len(prices) != len(signals):
        raise ValueError('prices and signals must have the same length')

    s = pd.Series(prices)
    sig = pd.Series(signals).fillna(0).astype(int)

    cash = float(initial_cash)
    pos = 0
    trades = []
    equity = []

    for t in range(len(s)):
        price = float(s.iloc[t])
        action = int(sig.iloc[t])

        if action == 1:
            qty = int(position_size)
            exec_price = price * (1.0 + slippage_pct)
            commission = exec_price * qty * commission_pct
            cost = exec_price * qty + commission
            if cost <= cash:
                cash -= cost
                pos += qty
                trades.append({'t': t, 'side': 'buy', 'qty': qty, 'price': exec_price, 'commission': commission})
        elif action == -1:
            if pos > 0:
                qty = pos
                exec_price = price * (1.0 - slippage_pct)
                commission = exec_price * qty * commission_pct
                proceeds = exec_price * qty - commission
                cash += proceeds
                trades.append({'t': t, 'side': 'sell', 'qty': qty, 'price': exec_price, 'commission': commission})
                pos = 0

        equity.append(cash + pos * price)

    eq = pd.Series(equity)
    returns = eq.pct_change().fillna(0)

    cum_return = float(eq.iloc[-1] / initial_cash - 1.0)
    sharpe = (returns.mean() / returns.std() * math.sqrt(252)) if returns.std() > 0 else None

    cummax = eq.cummax()
    drawdown = (eq - cummax) / cummax
    max_dd = float(drawdown.min()) if not drawdown.empty else 0.0

    return {
        'final_balance': float(eq.iloc[-1]) if not eq.empty else float(initial_cash),
        'equity_curve': eq.tolist(),
        'cum_return': cum_return,
        'sharpe': sharpe,
        'max_drawdown': max_dd,
        'trades': trades,
    }
