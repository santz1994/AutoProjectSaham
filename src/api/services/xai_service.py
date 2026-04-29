"""Explainable AI (XAI) Service for RL Trading Agent.

Provides SHAP-like feature importance explanations for RL agent decisions.
Generates human-readable narratives explaining why the agent decided to BUY/SELL/HOLD.

Part of Architecture Deep-Dive Layer 3: Explainable AI (XAI) Frontend Narration.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)

# Feature name mapping for human-readable output
_FEATURE_DISPLAY_NAMES = {
    "rsi": "RSI (Relative Strength Index)",
    "macd": "MACD Signal",
    "macd_hist": "MACD Histogram",
    "bb_width": "Bollinger Band Width",
    "dist_to_liquidation": "Distance to Liquidation",
    "norm_dist_to_liquidation": "Normalized Liquidation Distance",
    "volume": "Trading Volume",
    "close": "Close Price",
    "open": "Open Price",
    "high": "High Price",
    "low": "Low Price",
    "returns": "Price Returns",
    "volatility": "Volatility",
    "sentiment_score": "Market Sentiment (MiMo AI)",
    "confidence": "Sentiment Confidence",
    "risk_level": "Risk Level (MiMo)",
    "regime_trending": "Regime: Trending",
    "regime_ranging": "Regime: Ranging",
    "regime_volatile": "Regime: Volatile",
    "regime_crash": "Regime: Crash Protection",
    "momentum": "Momentum",
    "foreign_accumulation": "Foreign Accumulation",
    "net_foreign_volume": "Net Foreign Volume",
    "broker_activity": "Broker Activity",
}


@dataclass
class FeatureImportance:
    """A single feature's contribution to a decision."""
    name: str
    display_name: str
    value: float
    importance: float  # Absolute contribution magnitude
    direction: str  # "bullish", "bearish", "neutral"
    weight: float  # Normalized weight (0.0 - 1.0)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "display_name": self.display_name,
            "value": round(self.value, 6),
            "importance": round(self.importance, 6),
            "direction": self.direction,
            "weight": round(self.weight, 4),
        }


@dataclass
class XAIExplanation:
    """Complete explanation of an RL agent decision."""
    symbol: str
    action: str  # "BUY", "SELL", "HOLD"
    action_value: float  # Raw agent output (-1.0 to 1.0)
    target_fraction: float
    narrative: str
    feature_contributions: List[FeatureImportance]
    top_bullish: List[FeatureImportance]
    top_bearish: List[FeatureImportance]
    confidence_score: float
    risk_assessment: str
    regime_context: str
    supervisor_flags: List[str] = field(default_factory=list)
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbol": self.symbol,
            "action": self.action,
            "action_value": round(self.action_value, 4),
            "target_fraction": round(self.target_fraction, 4),
            "narrative": self.narrative,
            "feature_contributions": [f.to_dict() for f in self.feature_contributions],
            "top_bullish": [f.to_dict() for f in self.top_bullish],
            "top_bearish": [f.to_dict() for f in self.top_bearish],
            "confidence_score": round(self.confidence_score, 4),
            "risk_assessment": self.risk_assessment,
            "regime_context": self.regime_context,
            "supervisor_flags": self.supervisor_flags,
            "timestamp": self.timestamp,
        }


class XAIService:
    """Explainable AI Service for generating RL agent decision explanations.

    Computes feature importance via perturbation-based sensitivity analysis
    (SHAP-approximate) and generates natural language narratives using
    template-based reasoning.
    """

    def __init__(
        self,
        feature_names: Optional[List[str]] = None,
        top_k_features: int = 5,
        narrative_language: str = "en",
    ):
        """
        Args:
            feature_names: Ordered list of feature names matching observation space.
            top_k_features: Number of top features to highlight.
            narrative_language: Language for narratives ("en" or "id").
        """
        self.feature_names = feature_names or []
        self.top_k_features = top_k_features
        self.narrative_language = narrative_language
        self._explanation_history: List[XAIExplanation] = []
        self._total_explanations = 0

    def compute_feature_importance(
        self,
        observation: np.ndarray,
        agent_predict_fn,
        feature_names: Optional[List[str]] = None,
        n_perturbations: int = 50,
        perturbation_std: float = 0.1,
    ) -> List[FeatureImportance]:
        """Compute feature importance via perturbation-based sensitivity analysis.

        For each feature, perturb its value and measure the change in agent output.
        Features that cause larger output changes are more important.

        This is a simplified SHAP approximation suitable for real-time inference.

        Args:
            observation: Current observation vector (1D numpy array).
            agent_predict_fn: Function that takes observation → action value.
            feature_names: Optional override for feature names.
            n_perturbations: Number of perturbation samples per feature.
            perturbation_std: Standard deviation of perturbation noise.

        Returns:
            List of FeatureImportance sorted by importance (descending).
        """
        names = feature_names or self.feature_names
        if len(names) < len(observation):
            names = [names[i] if i < len(names) else f"feature_{i}" for i in range(len(observation))]

        # Baseline prediction
        baseline_action, _ = agent_predict_fn(observation)
        baseline_val = float(baseline_action[0]) if hasattr(baseline_action, '__len__') else float(baseline_action)

        contributions = []

        for i in range(min(len(observation), len(names))):
            feature_name = names[i] if i < len(names) else f"feature_{i}"
            original_val = float(observation[i])

            # Perturbation analysis
            action_diffs = []
            for _ in range(n_perturbations):
                perturbed = observation.copy()
                noise = np.random.normal(0, perturbation_std)
                perturbed[i] = original_val + noise

                try:
                    perturbed_action, _ = agent_predict_fn(perturbed)
                    perturbed_val = float(perturbed_action[0]) if hasattr(perturbed_action, '__len__') else float(perturbed_action)
                    action_diffs.append(perturbed_val - baseline_val)
                except Exception:
                    action_diffs.append(0.0)

            # Mean absolute contribution
            mean_contribution = float(np.mean(action_diffs))
            abs_contribution = abs(mean_contribution)

            # Determine direction
            if mean_contribution > 0.01:
                direction = "bullish"
            elif mean_contribution < -0.01:
                direction = "bearish"
            else:
                direction = "neutral"

            display_name = _FEATURE_DISPLAY_NAMES.get(feature_name, feature_name)

            contributions.append(FeatureImportance(
                name=feature_name,
                display_name=display_name,
                value=original_val,
                importance=abs_contribution,
                direction=direction,
                weight=0.0,  # Will be normalized below
            ))

        # Normalize weights
        total_importance = sum(c.importance for c in contributions)
        if total_importance > 0:
            for c in contributions:
                c.weight = c.importance / total_importance

        # Sort by importance descending
        contributions.sort(key=lambda x: x.importance, reverse=True)

        return contributions

    def generate_explanation(
        self,
        symbol: str,
        action_value: float,
        target_fraction: float,
        observation: np.ndarray,
        feature_contributions: List[FeatureImportance],
        regime: str = "unknown",
        supervisor_flags: Optional[List[str]] = None,
        stop_loss_distance: Optional[float] = None,
    ) -> XAIExplanation:
        """Generate a complete explanation for an RL agent decision.

        Args:
            symbol: Trading symbol (e.g., "BTC/USDT").
            action_value: Raw agent output (-1.0 to 1.0).
            target_fraction: Computed portfolio fraction.
            observation: Current observation vector.
            feature_contributions: Pre-computed feature importance list.
            regime: Current market regime.
            supervisor_flags: Any flags from MiMo supervisor or anomaly guard.
            stop_loss_distance: AI-computed stop-loss distance (if 2D action space).

        Returns:
            XAIExplanation with narrative and structured data.
        """
        # Determine action label
        if action_value > 0.1:
            action = "BUY"
        elif action_value < -0.1:
            action = "SELL"
        else:
            action = "HOLD"

        # Top features
        top_k = min(self.top_k_features, len(feature_contributions))
        top_features = feature_contributions[:top_k]
        top_bullish = [f for f in feature_contributions if f.direction == "bullish"][:3]
        top_bearish = [f for f in feature_contributions if f.direction == "bearish"][:3]

        # Confidence based on action magnitude and feature consensus
        bullish_weight = sum(f.weight for f in feature_contributions if f.direction == "bullish")
        bearish_weight = sum(f.weight for f in feature_contributions if f.direction == "bearish")
        consensus = abs(bullish_weight - bearish_weight)
        confidence = min(abs(action_value) * 0.5 + consensus * 0.5, 1.0)

        # Risk assessment
        risk_assessment = self._assess_risk(
            action_value, target_fraction, feature_contributions, regime, stop_loss_distance
        )

        # Regime context
        regime_context = self._describe_regime(regime, feature_contributions)

        # Generate narrative
        narrative = self._build_narrative(
            symbol=symbol,
            action=action,
            action_value=action_value,
            target_fraction=target_fraction,
            top_features=top_features,
            top_bullish=top_bullish,
            top_bearish=top_bearish,
            regime=regime,
            confidence=confidence,
            supervisor_flags=supervisor_flags or [],
            stop_loss_distance=stop_loss_distance,
        )

        explanation = XAIExplanation(
            symbol=symbol,
            action=action,
            action_value=action_value,
            target_fraction=target_fraction,
            narrative=narrative,
            feature_contributions=feature_contributions,
            top_bullish=top_bullish,
            top_bearish=top_bearish,
            confidence_score=confidence,
            risk_assessment=risk_assessment,
            regime_context=regime_context,
            supervisor_flags=supervisor_flags or [],
        )

        self._explanation_history.append(explanation)
        self._total_explanations += 1

        # Keep only last 100 explanations in memory
        if len(self._explanation_history) > 100:
            self._explanation_history = self._explanation_history[-100:]

        return explanation

    def _build_narrative(
        self,
        symbol: str,
        action: str,
        action_value: float,
        target_fraction: float,
        top_features: List[FeatureImportance],
        top_bullish: List[FeatureImportance],
        top_bearish: List[FeatureImportance],
        regime: str,
        confidence: float,
        supervisor_flags: List[str],
        stop_loss_distance: Optional[float],
    ) -> str:
        """Build a human-readable narrative explaining the decision."""
        parts = []

        # Opening statement
        strength = "strongly" if abs(action_value) > 0.7 else "moderately" if abs(action_value) > 0.3 else "slightly"
        pct = abs(target_fraction) * 100

        if action == "BUY":
            parts.append(
                f"RL Agent {strength} recommends BUY {symbol} — allocating {pct:.1f}% of portfolio."
            )
        elif action == "SELL":
            parts.append(
                f"RL Agent {strength} recommends SELL {symbol} — reducing position by {pct:.1f}%."
            )
        else:
            parts.append(
                f"RL Agent recommends HOLD {symbol} — maintaining current position."
            )

        # Key drivers
        if top_bullish:
            bullish_names = [f.display_name for f in top_bullish[:3]]
            parts.append(f"Bullish signals: {', '.join(bullish_names)}.")

        if top_bearish:
            bearish_names = [f.display_name for f in top_bearish[:3]]
            parts.append(f"Bearish signals: {', '.join(bearish_names)}.")

        # Sentiment context
        sentiment_feature = next(
            (f for f in top_features if "sentiment" in f.name.lower()), None
        )
        if sentiment_feature:
            if sentiment_feature.value > 0.3:
                parts.append("MiMo AI sentiment is positive, supporting the bullish case.")
            elif sentiment_feature.value < -0.3:
                parts.append("MiMo AI sentiment is negative, adding caution to the decision.")

        # Regime context
        if regime in ("trending", "volatile", "ranging", "crash"):
            parts.append(f"Market regime detected: {regime.upper()}.")

        # Stop-loss
        if stop_loss_distance is not None and action in ("BUY", "SELL"):
            sl_pct = stop_loss_distance * 100
            parts.append(f"AI-computed stop-loss distance: {sl_pct:.1f}%.")

        # Supervisor flags
        if supervisor_flags:
            flags_str = "; ".join(supervisor_flags[:3])
            parts.append(f"Supervisor alerts: {flags_str}")

        return " ".join(parts)

    def _assess_risk(
        self,
        action_value: float,
        target_fraction: float,
        features: List[FeatureImportance],
        regime: str,
        stop_loss_distance: Optional[float],
    ) -> str:
        """Assess overall risk level of the decision."""
        risk_score = 0.0

        # High leverage = high risk
        if abs(target_fraction) > 0.8:
            risk_score += 3
        elif abs(target_fraction) > 0.5:
            risk_score += 2
        elif abs(target_fraction) > 0.2:
            risk_score += 1

        # Volatile regime
        if regime == "volatile":
            risk_score += 2
        elif regime == "crash":
            risk_score += 4
        elif regime == "ranging":
            risk_score += 1

        # Close to liquidation
        liq_feature = next(
            (f for f in features if "liquidation" in f.name.lower()), None
        )
        if liq_feature and abs(liq_feature.value) < 0.2:
            risk_score += 3

        # Bearish consensus
        bearish_count = sum(1 for f in features if f.direction == "bearish")
        if bearish_count > len(features) * 0.6:
            risk_score += 2

        # Wide stop-loss = high risk tolerance
        if stop_loss_distance is not None and stop_loss_distance > 0.7:
            risk_score += 1

        if risk_score >= 7:
            return "EXTREME — High probability of significant loss. Consider reducing exposure."
        elif risk_score >= 5:
            return "HIGH — Elevated risk factors detected. Position sizing should be conservative."
        elif risk_score >= 3:
            return "MODERATE — Some risk factors present. Standard position management advised."
        else:
            return "LOW — Risk factors are within normal parameters."

    def _describe_regime(self, regime: str, features: List[FeatureImportance]) -> str:
        """Describe the market regime context."""
        regime_feature = next(
            (f for f in features if f"regime_{regime}" in f.name.lower()), None
        )

        descriptions = {
            "trending": "Market is in a trending state — momentum strategies may perform well.",
            "ranging": "Market is range-bound — mean-reversion strategies may be more effective.",
            "volatile": "Market is highly volatile — increased risk and opportunity. Tighter stops recommended.",
            "crash": "CRASH regime detected — capital preservation is priority. Reduced exposure advised.",
            "unknown": "Regime detection inconclusive — default risk management applies.",
        }

        return descriptions.get(regime, descriptions["unknown"])

    def get_history(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Get recent explanation history."""
        recent = self._explanation_history[-limit:]
        return [e.to_dict() for e in recent]

    def get_stats(self) -> Dict[str, Any]:
        """Return XAI service statistics."""
        return {
            "total_explanations": self._total_explanations,
            "history_size": len(self._explanation_history),
            "top_k_features": self.top_k_features,
            "feature_names_count": len(self.feature_names),
        }