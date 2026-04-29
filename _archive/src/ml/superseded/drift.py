"""Drift detection utilities for continuous training triggers.

Simple statistical drift detector using Kolmogorov-Smirnov test.
"""
from __future__ import annotations

from typing import Sequence

import numpy as np
from scipy.stats import ks_2samp


def detect_market_regime_drift(
    recent_returns: Sequence[float],
    baseline_returns: Sequence[float],
    threshold: float = 0.05,
) -> bool:
    """
    Return True when KS test indicates a significant distributional change.

    If drift detected, callers can trigger a retraining pipeline asynchronously.
    """
    try:
        recent = np.asarray(recent_returns, dtype=float)
        baseline = np.asarray(baseline_returns, dtype=float)
        if len(recent) < 10 or len(baseline) < 10:
            return False
        stat, pvalue = ks_2samp(recent, baseline)
        is_drifting = float(pvalue) < float(threshold)
        return bool(is_drifting)
    except Exception:
        return False
