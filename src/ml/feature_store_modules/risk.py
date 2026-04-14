"""Risk-oriented feature helpers for feature-store pipeline."""

from __future__ import annotations

import numpy as np

from .core_store import EPSILON, safe_float


def compute_dist_to_liquidation(
    current_price: float,
    entry_price: float,
    leverage: float = 10.0,
    maintenance_margin_rate: float = 0.005,
    side: str = "long",
) -> float:
    """Compute normalized distance from current price to liquidation level."""
    current = max(safe_float(current_price, 0.0), EPSILON)
    entry = max(safe_float(entry_price, current), EPSILON)
    lev = max(safe_float(leverage, 10.0), 1.0)
    mmr = float(np.clip(safe_float(maintenance_margin_rate, 0.005), 0.0, 0.99))
    side_normalized = str(side or "long").strip().lower()
    is_short = side_normalized in {"short", "sell"}

    if is_short:
        liquidation_price = entry * (1.0 + (1.0 / lev) - mmr)
        distance = (liquidation_price - current) / current
    else:
        liquidation_price = entry * (1.0 - (1.0 / lev) + mmr)
        distance = (current - liquidation_price) / current

    return safe_float(distance, 0.0)
