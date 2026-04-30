"""
Market Regime Detection module.

Extracted from agent_integration.py as part of the modularization effort.

Uses Gaussian Mixture Models (GMM) or statistical heuristics to detect
the current market regime:
- 0: Ranging / Sideways
- 1: Trending
- 2: Volatile
- 3: Crash / Crisis

The regime label is used by:
- TradingEnv (observation features, regime penalty)
- MimoSupervisor (veto conditions)
- AutonomyService (risk-based level adjustments)
- ContinuousAutoML (regime-aware training)
"""
from __future__ import annotations

import threading
from dataclasses import dataclass, field

import numpy as np


@dataclass
class RegimeState:
    """Current regime detection state."""
    label: int = 0            # 0=ranging, 1=trending, 2=volatile, 3=crash
    confidence: float = 0.0   # 0.0-1.0
    risk_score: float = 0.0   # 0.0-1.0, higher = more risky
    volatility: float = 0.0
    trend_strength: float = 0.0
    details: dict = field(default_factory=dict)


class RegimeDetector:
    """
    Market regime detector using statistical features.

    Analyzes recent price data to classify the current market state
    into one of 4 regimes. Uses rolling window statistics:
    - Volatility (rolling std of returns)
    - Trend strength (rolling mean of returns, directional)
    - Drawdown magnitude
    """

    def __init__(self, window_size: int = 50, volatility_threshold: float = 0.02,
                 trend_threshold: float = 0.005, crash_threshold: float = 0.1):
        self.window_size = window_size
        self.volatility_threshold = volatility_threshold
        self.trend_threshold = trend_threshold
        self.crash_threshold = crash_threshold

        self._price_history: dict[str, list[float]] = {}
        self._return_history: dict[str, list[float]] = {}
        self._current_state: dict[str, RegimeState] = {}
        self._lock = threading.Lock()

    def update(self, symbol: str, price: float) -> RegimeState:
        """
        Update regime detector with new price data.

        Args:
            symbol: Trading symbol.
            price: Current price.

        Returns:
            Updated RegimeState for the symbol.
        """
        with self._lock:
            if symbol not in self._price_history:
                self._price_history[symbol] = []
                self._return_history[symbol] = []

            prices = self._price_history[symbol]
            returns = self._return_history[symbol]

            prices.append(price)

            if len(prices) >= 2:
                ret = (prices[-1] - prices[-2]) / max(prices[-2], 1e-8)
                returns.append(ret)

            # Keep only window_size data points
            if len(prices) > self.window_size * 2:
                self._price_history[symbol] = prices[-self.window_size:]
                self._return_history[symbol] = returns[-self.window_size:]
                prices = self._price_history[symbol]
                returns = self._return_history[symbol]

            # Compute regime
            state = self._classify(returns, prices)
            self._current_state[symbol] = state
            return state

    def get_state(self, symbol: str) -> RegimeState:
        """Get current regime state for a symbol."""
        with self._lock:
            return self._current_state.get(symbol, RegimeState())

    def get_label(self, symbol: str) -> int:
        """Get current regime label (0-3) for a symbol."""
        return self.get_state(symbol).label

    def get_risk_score(self, symbol: str) -> float:
        """Get current risk score (0.0-1.0) for a symbol."""
        return self.get_state(symbol).risk_score

    def _classify(self, returns: list[float], prices: list[float]) -> RegimeState:
        """Classify the current market regime based on return statistics."""
        if len(returns) < 10:
            return RegimeState(label=0, confidence=0.1, risk_score=0.1)

        arr = np.array(returns[-self.window_size:], dtype=np.float64)

        # Volatility: rolling standard deviation
        volatility = float(np.std(arr))

        # Trend strength: mean return * sqrt(n) — measures significance
        mean_return = float(np.mean(arr))
        trend_strength = abs(mean_return) * np.sqrt(len(arr))

        # Max drawdown in window
        price_arr = np.array(prices[-self.window_size:], dtype=np.float64)
        if len(price_arr) > 1:
            peak = np.maximum.accumulate(price_arr)
            drawdown = (peak - price_arr) / np.maximum(peak, 1e-8)
            max_drawdown = float(np.max(drawdown))
        else:
            max_drawdown = 0.0

        # Classification logic
        risk_score = min(1.0, (volatility / max(self.volatility_threshold, 1e-8)) * 0.5
                         + max_drawdown * 0.5)

        # Crash detection
        if max_drawdown > self.crash_threshold or volatility > self.volatility_threshold * 5:
            label = 3  # crash
            confidence = min(1.0, max_drawdown / self.crash_threshold)
        # Volatile detection
        elif volatility > self.volatility_threshold * 2:
            label = 2  # volatile
            confidence = min(1.0, volatility / (self.volatility_threshold * 3))
        # Trending detection
        elif trend_strength > self.trend_threshold:
            label = 1  # trending
            confidence = min(1.0, trend_strength / (self.trend_threshold * 2))
        # Ranging (default)
        else:
            label = 0  # ranging
            confidence = 1.0 - min(1.0, volatility / self.volatility_threshold)

        return RegimeState(
            label=label,
            confidence=confidence,
            risk_score=risk_score,
            volatility=volatility,
            trend_strength=trend_strength,
            details={
                "max_drawdown": max_drawdown,
                "mean_return": mean_return,
                "window_size": len(returns),
            },
        )

    def get_all_states(self) -> dict[str, RegimeState]:
        """Get regime states for all tracked symbols."""
        with self._lock:
            return dict(self._current_state)

    def reset(self, symbol: str | None = None) -> None:
        """Reset history for a symbol or all symbols."""
        with self._lock:
            if symbol:
                self._price_history.pop(symbol, None)
                self._return_history.pop(symbol, None)
                self._current_state.pop(symbol, None)
            else:
                self._price_history.clear()
                self._return_history.clear()
                self._current_state.clear()