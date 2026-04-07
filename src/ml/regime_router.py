"""Lightweight market regime classifier and agent router.

This module is dependency-light and designed for online inference paths.
It classifies regime from recent prices and provides a routing profile that
upstream signal generators can use to adjust aggression.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List, Tuple

import numpy as np


VALID_SIGNALS = {"STRONG_BUY", "BUY", "HOLD", "SELL", "STRONG_SELL"}


@dataclass(frozen=True)
class AgentRouteSnapshot:
    regime: str
    confidence: float
    primary_agent: str
    strategy_profile: str
    risk_multiplier: float
    trend_return: float
    volatility: float
    up_move_ratio: float


def _clip(value: float, low: float, high: float) -> float:
    return float(max(low, min(high, value)))


def classify_market_regime(
    prices: Iterable[float],
    lookback: int = 30,
) -> AgentRouteSnapshot:
    """Classify market regime and return routing profile.

    Regime outputs:
    - BULL: route to bull agent / momentum strategy
    - BEAR: route to bear agent / defensive strategy
    - SIDEWAYS: route to scalper agent / mean-reversion strategy
    """
    finite_prices: List[float] = []
    for value in prices:
        try:
            parsed = float(value)
        except Exception:
            continue
        if np.isfinite(parsed) and parsed > 0:
            finite_prices.append(parsed)

    if len(finite_prices) < 3:
        return AgentRouteSnapshot(
            regime="SIDEWAYS",
            confidence=0.45,
            primary_agent="scalper_agent",
            strategy_profile="mean_reversion_swing",
            risk_multiplier=0.75,
            trend_return=0.0,
            volatility=0.0,
            up_move_ratio=0.5,
        )

    price_arr = np.asarray(finite_prices, dtype=float)
    returns = np.diff(price_arr) / np.maximum(price_arr[:-1], 1e-9)
    window = returns[-max(3, int(lookback)) :]

    trend_return = float(np.mean(window))
    volatility = float(np.std(window))
    up_move_ratio = float(np.mean(window > 0)) if len(window) > 0 else 0.5

    bull_cond = trend_return > 0.001 and up_move_ratio >= 0.55
    bear_cond = trend_return < -0.001 and up_move_ratio <= 0.45

    momentum_score = abs(trend_return) / max(volatility, 1e-6)

    if bull_cond:
        confidence = _clip(
            0.45 + min(0.40, momentum_score * 0.18) + min(0.15, (up_move_ratio - 0.5) * 0.6),
            0.45,
            0.95,
        )
        return AgentRouteSnapshot(
            regime="BULL",
            confidence=confidence,
            primary_agent="bull_agent",
            strategy_profile="momentum_breakout",
            risk_multiplier=1.0,
            trend_return=trend_return,
            volatility=volatility,
            up_move_ratio=up_move_ratio,
        )

    if bear_cond:
        confidence = _clip(
            0.45 + min(0.40, momentum_score * 0.18) + min(0.15, (0.5 - up_move_ratio) * 0.6),
            0.45,
            0.95,
        )
        return AgentRouteSnapshot(
            regime="BEAR",
            confidence=confidence,
            primary_agent="bear_agent",
            strategy_profile="defensive_rotation",
            risk_multiplier=0.55,
            trend_return=trend_return,
            volatility=volatility,
            up_move_ratio=up_move_ratio,
        )

    balance_score = 1.0 - min(1.0, abs(up_move_ratio - 0.5) * 2.0)
    low_trend_score = 1.0 - min(1.0, abs(trend_return) / 0.01)
    confidence = _clip(0.40 + (0.35 * balance_score) + (0.25 * low_trend_score), 0.40, 0.90)

    return AgentRouteSnapshot(
        regime="SIDEWAYS",
        confidence=confidence,
        primary_agent="scalper_agent",
        strategy_profile="mean_reversion_swing",
        risk_multiplier=0.75,
        trend_return=trend_return,
        volatility=volatility,
        up_move_ratio=up_move_ratio,
    )


def apply_regime_overlay(
    signal: str,
    expected_return: float,
    model_confidence: float,
    route: AgentRouteSnapshot,
) -> Tuple[str, float, str]:
    """Adjust signal aggressiveness with regime routing context."""
    normalized_signal = str(signal or "HOLD").upper()
    if normalized_signal not in VALID_SIGNALS:
        normalized_signal = "HOLD"

    adjusted_return = _clip(float(expected_return) * float(route.risk_multiplier), -0.30, 0.30)
    note = (
        f"Regime {route.regime} (conf {route.confidence * 100:.1f}%) -> "
        f"{route.primary_agent}/{route.strategy_profile}."
    )

    conf = float(model_confidence)

    if route.regime == "BEAR":
        if normalized_signal in {"BUY", "STRONG_BUY"} and conf < 0.85:
            normalized_signal = "HOLD"
            adjusted_return = min(adjusted_return, 0.0)
            note += " Long bias ditahan pada market bearish."
        elif normalized_signal == "STRONG_BUY":
            normalized_signal = "BUY"
            note += " Strong buy diturunkan jadi buy pada regime bearish."
    elif route.regime == "BULL":
        if normalized_signal in {"SELL", "STRONG_SELL"} and conf < 0.85:
            normalized_signal = "HOLD"
            adjusted_return = max(adjusted_return, 0.0)
            note += " Short bias ditahan pada market bullish."
        elif normalized_signal == "STRONG_SELL":
            normalized_signal = "SELL"
            note += " Strong sell diturunkan jadi sell pada regime bullish."
    else:
        if normalized_signal == "STRONG_BUY":
            normalized_signal = "BUY"
            note += " Strong buy diturunkan untuk kondisi range-bound."
        elif normalized_signal == "STRONG_SELL":
            normalized_signal = "SELL"
            note += " Strong sell diturunkan untuk kondisi range-bound."

    return normalized_signal, float(adjusted_return), note
