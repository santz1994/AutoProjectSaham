"""
MiMo Supervisor Agent — Fat Tail Risk Protection (Layer 2).

Extracted from agent_integration.py as part of the modularization effort.

The MiMo Supervisor runs parallel with the RL agent + Anomaly Detector.
Before process_action() executes an order to the exchange, the supervisor
checks for extreme conditions and can:
- Veto the trade entirely
- Cut the sizing (target_fraction *= 0.25 or *= 0.5)
- Allow the trade to proceed unchanged

Veto conditions:
1. Extreme negative sentiment (sentiment_score < -0.8)
2. Extreme risk level (risk_level > 0.9)
3. Sentiment divergence from RL action (BUY but sentiment very bearish, or vice versa)
"""
from __future__ import annotations

import threading
from dataclasses import dataclass, field


@dataclass
class SupervisorDecision:
    """Result of supervisor check."""
    vetoed: bool = False
    adjusted_fraction: float = 1.0
    reason: str = ""


class MimoSupervisor:
    """
    MiMo Supervisor Agent — parallel fat-tail risk protection.

    Runs alongside RL agent. Can veto or reduce position sizes based on
    sentiment conditions (extreme negative sentiment, extreme risk,
    sentiment-action divergence).
    """

    def __init__(self, veto_threshold: float = -0.8, risk_threshold: float = 0.9,
                 divergence_threshold: float = 0.7):
        self.veto_threshold = veto_threshold
        self.risk_threshold = risk_threshold
        self.divergence_threshold = divergence_threshold

        # Latest sentiment data (injected from SentimentScheduler)
        self._latest_sentiment: dict[str, dict] = {}
        self._lock = threading.Lock()

        # Stats
        self.check_count = 0
        self.veto_count = 0
        self.cut_count = 0
        self.last_veto_reason = ""

    def set_latest_sentiment(self, symbol: str, sentiment_data: dict) -> None:
        """Inject latest sentiment data for a symbol."""
        with self._lock:
            self._latest_sentiment[symbol] = sentiment_data

    def should_veto(self, symbol: str, target_fraction: float,
                    current_prices: dict[str, float] | None = None) -> tuple[bool, float, str]:
        """
        Check if a trade should be vetoed or reduced.

        Args:
            symbol: Trading symbol.
            target_fraction: Proposed position fraction (0.0-1.0).
            current_prices: Current market prices (for context).

        Returns:
            (vetoed, adjusted_fraction, reason)
        """
        with self._lock:
            self.check_count += 1

        sentiment = self._latest_sentiment.get(symbol)
        if not sentiment:
            return False, target_fraction, ""

        sentiment_score = sentiment.get("sentiment_score", 0.0)
        risk_level = sentiment.get("risk_level", 0.0)
        confidence = sentiment.get("confidence", 0.5)

        # Condition 1: Extreme negative sentiment → VETO
        if sentiment_score < self.veto_threshold:
            with self._lock:
                self.veto_count += 1
                self.last_veto_reason = f"extreme_negative_sentiment({sentiment_score:.2f})"
            return True, 0.0, self.last_veto_reason

        # Condition 2: Extreme risk level → severe cut
        if risk_level > self.risk_threshold:
            with self._lock:
                self.cut_count += 1
            adjusted = target_fraction * 0.25
            reason = f"extreme_risk({risk_level:.2f})_cut_to_{adjusted:.4f}"
            return False, adjusted, reason

        # Condition 3: Sentiment-action divergence
        # BUY signal but very bearish sentiment (or vice versa)
        if target_fraction > 0.1 and sentiment_score < -self.divergence_threshold:
            with self._lock:
                self.cut_count += 1
            adjusted = target_fraction * 0.5
            reason = f"sentiment_divergence_buy_but_bearish({sentiment_score:.2f})"
            return False, adjusted, reason

        if target_fraction < -0.1 and sentiment_score > self.divergence_threshold:
            with self._lock:
                self.cut_count += 1
            adjusted = target_fraction * 0.5
            reason = f"sentiment_divergence_sell_but_bullish({sentiment_score:.2f})"
            return False, adjusted, reason

        # No veto needed
        return False, target_fraction, ""

    def get_stats(self) -> dict:
        """Return supervisor statistics."""
        with self._lock:
            return {
                "check_count": self.check_count,
                "veto_count": self.veto_count,
                "cut_count": self.cut_count,
                "last_veto_reason": self.last_veto_reason,
                "active_symbols": list(self._latest_sentiment.keys()),
            }

    def reset_stats(self) -> None:
        """Reset statistics."""
        with self._lock:
            self.check_count = 0
            self.veto_count = 0
            self.cut_count = 0
            self.last_veto_reason = ""