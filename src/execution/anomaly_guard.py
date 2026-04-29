"""
Anomaly Execution Guard — Fat Tail Risk Protection

Sits between RL Agent prediction and order execution.
If anomaly detected → reduce position size or kill the trade entirely.

Architecture:
  RL Agent predict → Anomaly Guard → (pass/reduce/veto) → Execution Manager

This prevents the "90% winrate trap" where agent wins small many times
then loses everything in one fat-tail event (flash crash, hack, etc).
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

import numpy as np

try:
    import pandas as pd
except ImportError:
    pd = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)


class GuardDecision(str, Enum):
    """Decision from the anomaly guard."""
    PASS = "pass"            # No anomaly, proceed normally
    REDUCE = "reduce"        # Anomaly detected, reduce position size
    VETO = "veto"            # Critical anomaly, block the trade entirely


@dataclass
class GuardResult:
    """Result of anomaly guard evaluation."""
    decision: GuardDecision
    original_fraction: float
    adjusted_fraction: float
    anomaly_types: List[str] = field(default_factory=list)
    anomaly_score: float = 0.0
    risk_multiplier: float = 1.0
    reason: str = ""
    details: Dict[str, Any] = field(default_factory=dict)

    @property
    def is_blocked(self) -> bool:
        return self.decision == GuardDecision.VETO

    @property
    def is_reduced(self) -> bool:
        return self.decision == GuardDecision.REDUCE

    def to_dict(self) -> Dict[str, Any]:
        return {
            "decision": self.decision.value,
            "original_fraction": self.original_fraction,
            "adjusted_fraction": self.adjusted_fraction,
            "anomaly_types": self.anomaly_types,
            "anomaly_score": self.anomaly_score,
            "risk_multiplier": self.risk_multiplier,
            "reason": self.reason,
        }


class AnomalyExecutionGuard:
    """
    Production guard that evaluates market anomalies before order execution.
    
    Integrates:
    - AnomalyRiskManager (IsolationForest + Autoencoder + Statistical)
    - MiMo Supervisor veto signal
    - Configurable thresholds for pass/reduce/veto
    
    Usage:
        guard = AnomalyExecutionGuard()
        guard.fit(historical_features)
        
        # In trading loop:
        result = guard.evaluate(
            target_fraction=rl_agent.predict(obs),
            features=current_features,
            prices=recent_prices,
            volumes=recent_volumes,
        )
        if not result.is_blocked:
            execute_order(result.adjusted_fraction)
    """

    def __init__(
        self,
        veto_threshold: float = 0.8,
        reduce_threshold: float = 0.4,
        min_risk_multiplier: float = 0.1,
        enable_mimo_veto: bool = True,
        anomaly_contamination: float = 0.05,
    ):
        """
        Initialize anomaly execution guard.
        
        Args:
            veto_threshold: Anomaly score above this → block trade entirely
            reduce_threshold: Anomaly score above this → reduce position size
            min_risk_multiplier: Minimum risk multiplier when reducing
            enable_mimo_veto: Whether to check MiMo supervisor veto
            anomaly_contamination: Expected outlier proportion for detectors
        """
        self.veto_threshold = veto_threshold
        self.reduce_threshold = reduce_threshold
        self.min_risk_multiplier = min_risk_multiplier
        self.enable_mimo_veto = enable_mimo_veto

        # Lazy-init anomaly risk manager
        self._risk_manager = None
        self._contamination = anomaly_contamination
        self._is_fitted = False

        # MiMo supervisor veto state (updated externally)
        self.mimo_veto_active: bool = False
        self.mimo_veto_reason: str = ""
        self.mimo_veto_severity: float = 0.0

        # Stats
        self.stats = {
            "total_evaluations": 0,
            "pass_count": 0,
            "reduce_count": 0,
            "veto_count": 0,
            "mimo_veto_count": 0,
            "last_evaluation_ts": 0.0,
        }

        # History for diagnostics
        self.history: List[GuardResult] = []
        self._max_history = 500

    def _ensure_risk_manager(self):
        """Lazy-initialize AnomalyRiskManager."""
        if self._risk_manager is None:
            try:
                from src.ml.anomaly_detector import AnomalyRiskManager
                self._risk_manager = AnomalyRiskManager(
                    isolation_contamination=self._contamination,
                    autoencoder_enabled=False,  # Start with IsolationForest only
                    risk_reduction_factor=0.5,
                    ensemble_method="voting",
                )
                logger.info("AnomalyRiskManager initialized (IsolationForest mode)")
            except Exception as e:
                logger.warning(f"Failed to init AnomalyRiskManager: {e}")
                self._risk_manager = None

    def fit(self, features: "pd.DataFrame") -> None:
        """
        Fit anomaly detectors on historical feature data.
        
        Args:
            features: DataFrame of historical features (same features as RL observation)
        """
        self._ensure_risk_manager()
        if self._risk_manager is not None:
            try:
                self._risk_manager.fit(features)
                self._is_fitted = True
                logger.info(f"AnomalyExecutionGuard fitted on {len(features)} samples")
            except Exception as e:
                logger.error(f"Failed to fit anomaly guard: {e}")
                self._is_fitted = False

    def update_mimo_veto(
        self,
        veto_active: bool,
        reason: str = "",
        severity: float = 0.0,
    ) -> None:
        """
        Update MiMo supervisor veto signal (called from SentimentScheduler).
        
        Args:
            veto_active: True if MiMo recommends blocking trades
            reason: Why the veto was triggered
            severity: 0.0 to 1.0 severity score
        """
        self.mimo_veto_active = veto_active
        self.mimo_veto_reason = reason
        self.mimo_veto_severity = severity
        if veto_active:
            logger.warning(f"MiMo Supervisor VETO activated: {reason} (severity={severity:.2f})")

    def evaluate(
        self,
        target_fraction: float,
        features: Optional[Any] = None,
        prices: Optional[np.ndarray] = None,
        volumes: Optional[np.ndarray] = None,
    ) -> GuardResult:
        """
        Evaluate whether a trade should proceed, be reduced, or be blocked.
        
        Args:
            target_fraction: RL agent's target position fraction
            features: Current market features (DataFrame or numpy array)
            prices: Recent price series
            volumes: Recent volume series
            
        Returns:
            GuardResult with decision and adjusted fraction
        """
        self.stats["total_evaluations"] += 1
        self.stats["last_evaluation_ts"] = time.time()

        anomaly_score = 0.0
        anomaly_types: List[str] = []
        risk_multiplier = 1.0
        details: Dict[str, Any] = {}

        # 1. Check MiMo supervisor veto FIRST (highest priority)
        if self.enable_mimo_veto and self.mimo_veto_active:
            self.stats["mimo_veto_count"] += 1
            result = GuardResult(
                decision=GuardDecision.VETO,
                original_fraction=target_fraction,
                adjusted_fraction=0.0,
                anomaly_types=["mimo_supervisor_veto"],
                anomaly_score=self.mimo_veto_severity,
                risk_multiplier=0.0,
                reason=f"MiMo Supervisor veto: {self.mimo_veto_reason}",
                details={"mimo_severity": self.mimo_veto_severity},
            )
            self._record(result)
            return result

        # 2. Run anomaly detection (if fitted and features available)
        if self._is_fitted and self._risk_manager is not None and features is not None:
            try:
                if pd is None:
                    raise ImportError("pandas required for anomaly detection")

                if isinstance(features, np.ndarray):
                    # Convert numpy to DataFrame with generic column names
                    if features.ndim == 1:
                        features = features.reshape(1, -1)
                    col_names = [f"f_{i}" for i in range(features.shape[1])]
                    features_df = pd.DataFrame(features, columns=col_names)
                elif isinstance(features, pd.DataFrame):
                    features_df = features
                else:
                    features_df = pd.DataFrame(features)

                detect_result = self._risk_manager.detect_anomalies(
                    features=features_df,
                    prices=prices,
                    volumes=volumes,
                )

                anomaly_score = detect_result.get("anomaly_score", 0.0)
                anomaly_types = detect_result.get("anomaly_types", [])
                risk_multiplier = detect_result.get("risk_multiplier", 1.0)
                details = detect_result.get("details", {})

            except Exception as e:
                logger.warning(f"Anomaly detection failed: {e}")
                # Graceful degradation — allow trade to proceed
                anomaly_score = 0.0

        # 3. Decision logic
        if anomaly_score >= self.veto_threshold:
            # CRITICAL anomaly → VETO (block trade entirely)
            self.stats["veto_count"] += 1
            result = GuardResult(
                decision=GuardDecision.VETO,
                original_fraction=target_fraction,
                adjusted_fraction=0.0,
                anomaly_types=anomaly_types,
                anomaly_score=anomaly_score,
                risk_multiplier=0.0,
                reason=f"Critical anomaly (score={anomaly_score:.2f}): {anomaly_types}",
                details=details,
            )
        elif anomaly_score >= self.reduce_threshold:
            # MODERATE anomaly → REDUCE position size
            self.stats["reduce_count"] += 1
            effective_multiplier = max(self.min_risk_multiplier, risk_multiplier)
            adjusted = target_fraction * effective_multiplier
            result = GuardResult(
                decision=GuardDecision.REDUCE,
                original_fraction=target_fraction,
                adjusted_fraction=adjusted,
                anomaly_types=anomaly_types,
                anomaly_score=anomaly_score,
                risk_multiplier=effective_multiplier,
                reason=f"Moderate anomaly (score={anomaly_score:.2f}), reduced by {effective_multiplier:.2f}x",
                details=details,
            )
        else:
            # NO anomaly → PASS
            self.stats["pass_count"] += 1
            result = GuardResult(
                decision=GuardDecision.PASS,
                original_fraction=target_fraction,
                adjusted_fraction=target_fraction,
                anomaly_types=[],
                anomaly_score=anomaly_score,
                risk_multiplier=1.0,
                reason="No anomaly detected",
            )

        self._record(result)
        return result

    def _record(self, result: GuardResult) -> None:
        """Record result in history."""
        self.history.append(result)
        if len(self.history) > self._max_history:
            self.history = self.history[-self._max_history:]

        if result.decision != GuardDecision.PASS:
            logger.warning(
                f"AnomalyGuard [{result.decision.value.upper()}]: "
                f"fraction {result.original_fraction:.4f} → {result.adjusted_fraction:.4f} | "
                f"types={result.anomaly_types} | score={result.anomaly_score:.2f}"
            )

    def get_stats(self) -> Dict[str, Any]:
        """Get guard statistics."""
        return {
            **self.stats,
            "is_fitted": self._is_fitted,
            "mimo_veto_active": self.mimo_veto_active,
            "pass_rate": (
                self.stats["pass_count"] / max(1, self.stats["total_evaluations"])
            ),
        }

    def get_recent_blocks(self, n: int = 10) -> List[Dict[str, Any]]:
        """Get recent non-pass decisions."""
        blocked = [r for r in self.history if r.decision != GuardDecision.PASS]
        return [r.to_dict() for r in blocked[-n:]]