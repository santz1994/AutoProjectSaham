"""SHAP explainer utilities for tree-based models.

Provides a small wrapper to produce top feature drivers for a single prediction.
"""
from __future__ import annotations

from typing import Dict, List

import numpy as np
import pandas as pd

try:
    import shap
except Exception:
    shap = None


def generate_trade_explanation(model, current_features: pd.DataFrame, feature_names: List[str]) -> Dict:
    """
    Return a compact SHAP-based explanation for the latest row in `current_features`.

    If SHAP is not available, returns a minimal fallback.
    """
    if shap is None:
        return {
            'base_value': None,
            'top_bullish_drivers': [],
            'top_bearish_drivers': [],
            'note': 'shap not installed',
        }

    explainer = shap.TreeExplainer(model)
    shap_values = explainer.shap_values(current_features)

    # handle binary classifiers where shap_values is a list
    if isinstance(shap_values, list):
        cls_idx = 1 if len(shap_values) > 1 else 0
        vals = shap_values[cls_idx]
    else:
        vals = shap_values

    last_vals = vals[-1]

    feature_impact = sorted(
        zip(feature_names, last_vals), key=lambda x: abs(x[1]), reverse=True
    )

    top_bullish = [{'feature': f, 'impact': float(v)} for f, v in feature_impact if v > 0][:3]
    top_bearish = [{'feature': f, 'impact': float(v)} for f, v in feature_impact if v < 0][:3]

    base_value = None
    try:
        ev = explainer.expected_value
        if isinstance(ev, (list, tuple)):
            base_value = float(ev[1]) if len(ev) > 1 else float(ev[0])
        else:
            base_value = float(ev)
    except Exception:
        base_value = None

    return {
        'base_value': base_value,
        'top_bullish_drivers': top_bullish,
        'top_bearish_drivers': top_bearish,
    }
