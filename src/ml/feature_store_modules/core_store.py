"""Core helpers for feature-store modular pipeline."""

from __future__ import annotations

from typing import Any, Dict, List

import numpy as np

EPSILON = 1e-9
NUMERIC_TYPES = (int, float, np.number)


def safe_float(value: Any, default: float = 0.0) -> float:
    """Cast value to finite float with a safe fallback."""
    try:
        casted = float(value)
    except (TypeError, ValueError):
        return float(default)
    if not np.isfinite(casted):
        return float(default)
    return float(casted)


def clip_unit(value: float) -> float:
    """Clip numeric value into [-1, 1]."""
    return float(np.clip(safe_float(value, 0.0), -1.0, 1.0))


def symbol_base(symbol: str) -> str:
    """Normalize symbol to canonical base token."""
    normalized = str(symbol or "").strip().upper()
    if not normalized:
        return normalized

    if normalized.endswith("=X"):
        normalized = normalized[:-2]

    if "/" in normalized:
        return normalized.replace("/", "")
    if "-USD" in normalized:
        return normalized.split("-USD", 1)[0]
    if normalized.endswith("USDT") and len(normalized) > 4:
        return normalized[:-4]
    if "." in normalized:
        return normalized.split(".", 1)[0]
    return normalized


def symbol_aliases(symbol: str) -> List[str]:
    """Generate common alias representations for a symbol."""
    normalized = str(symbol or "").strip().upper()
    if not normalized:
        return []

    aliases: List[str] = [normalized]
    base = symbol_base(normalized)
    if base:
        aliases.append(base)
        aliases.append(f"{base}-USD")
        aliases.append(f"{base}/USDT")
        aliases.append(f"{base}USDT")
        if len(base) == 6 and base.isalpha():
            aliases.append(f"{base}=X")
            aliases.append(f"{base[:3]}/{base[3:]}")

    if "/" in normalized:
        aliases.append(normalized.replace("/", ""))
    if "-USD" in normalized:
        aliases.append(normalized.replace("-USD", ""))

    deduped: List[str] = []
    for item in aliases:
        if item and item not in deduped:
            deduped.append(item)
    return deduped


def normalize_feature_vector(features: Dict[str, Any]) -> Dict[str, float]:
    """Normalize numeric feature dictionary into bounded values [-1, 1]."""
    if not features:
        return {}

    last_price = max(safe_float(features.get("last_price"), 1.0), EPSILON)
    normalized: Dict[str, float] = {}

    for key, value in features.items():
        if not isinstance(value, NUMERIC_TYPES):
            continue
        val = safe_float(value)

        if key == "rsi_14":
            n_val = (val - 50.0) / 50.0
        elif key in {
            "last_price",
            "short_sma",
            "long_sma",
            "bb_upper",
            "bb_lower",
            "vwap",
        }:
            n_val = np.tanh(((val / last_price) - 1.0) * 10.0)
        elif key in {"macd", "macd_signal"}:
            n_val = np.tanh((val / last_price) * 80.0)
        elif key in {"bb_width"}:
            n_val = np.tanh((val / last_price) * 20.0)
        elif key in {
            "momentum",
            "horizon_return",
            "horizon_max_drawdown",
            "horizon_trend_slope",
            "vwap_deviation",
        }:
            n_val = np.tanh(val * 10.0)
        elif key in {
            "volatility",
            "horizon_volatility",
            "horizon_range_pct",
            "price_impact",
            "amihud_illiquidity",
        }:
            n_val = np.tanh(val * 50.0)
        elif key in {"sma_ratio", "horizon_volume_ratio", "price_to_vwap_ratio"}:
            n_val = np.tanh((val - 1.0) * 10.0)
        elif key in {"avg_vol_5", "horizon_avg_volume"}:
            n_val = np.tanh(np.log1p(max(val, 0.0)) / 10.0)
        elif key in {"dist_to_liquidation", "order_flow_imbalance"}:
            n_val = np.clip(val, -1.0, 1.0)
        elif key.startswith("has_"):
            n_val = np.clip(val, 0.0, 1.0)
        elif key in {"n_obs", "horizon_window_bars", "horizon_bars"}:
            n_val = np.clip(val / 200.0, 0.0, 1.0)
        else:
            n_val = np.tanh(val)

        normalized[f"norm_{key}"] = clip_unit(float(n_val))

    return normalized
