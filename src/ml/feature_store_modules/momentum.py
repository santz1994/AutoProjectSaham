"""Momentum/horizon feature helpers for feature-store pipeline."""

from __future__ import annotations

from typing import Dict, List, Optional

import numpy as np
import pandas as pd  # type: ignore[import-untyped]

from .core_store import safe_float


def compute_horizon_features(
    prices: List[float],
    volumes: Optional[List[float]] = None,
    horizon_bars: int = 5,
) -> Dict[str, float]:
    """Compute horizon-aware features for configurable prediction windows."""
    if not prices:
        return {}

    try:
        bars = max(1, int(horizon_bars))
    except (TypeError, ValueError):
        bars = 5

    series = pd.Series(prices, dtype=float).dropna()
    n_obs = len(series)
    if n_obs < 2:
        return {}

    lookback = min(bars, n_obs - 1)
    start_idx = n_obs - (lookback + 1)
    segment = series.iloc[start_idx:]

    start_price = float(segment.iloc[0])
    end_price = float(segment.iloc[-1])
    denom = max(abs(start_price), 1.0)

    horizon_return = float((end_price / start_price) - 1.0) if start_price != 0 else 0.0

    seg_returns = segment.pct_change().dropna()
    if len(seg_returns) >= 2:
        horizon_volatility = float(seg_returns.std())
    elif len(seg_returns) == 1:
        horizon_volatility = float(abs(seg_returns.iloc[-1]))
    else:
        horizon_volatility = 0.0

    running_max = segment.cummax().replace(0, np.nan)
    drawdowns = (segment / running_max - 1.0).fillna(0.0)
    horizon_max_drawdown = float(drawdowns.min())

    seg_min = float(segment.min())
    seg_max = float(segment.max())
    horizon_range_pct = float((seg_max - seg_min) / denom)

    horizon_trend_slope = 0.0
    if len(segment) >= 3:
        x_axis = np.arange(len(segment), dtype=float)
        y_axis = segment.to_numpy(dtype=float)
        if np.isfinite(y_axis).all():
            slope = float(np.polyfit(x_axis, y_axis, 1)[0])
            horizon_trend_slope = float(slope / denom)

    horizon_avg_volume = 0.0
    horizon_volume_ratio = 1.0
    if volumes:
        try:
            vol_series = pd.Series(volumes, dtype=float).dropna()
            if len(vol_series) > 0:
                recent_vol = vol_series.tail(lookback)
                horizon_avg_volume = float(recent_vol.mean())
                if len(vol_series) >= (lookback * 2):
                    baseline_vol = vol_series.iloc[-(lookback * 2) : -lookback]
                    baseline = float(baseline_vol.mean())
                else:
                    baseline = float(vol_series.mean())

                if baseline and not np.isnan(baseline):
                    horizon_volume_ratio = float(horizon_avg_volume / baseline)
        except (TypeError, ValueError):
            horizon_avg_volume = 0.0
            horizon_volume_ratio = 1.0

    return {
        "horizon_return": safe_float(horizon_return, 0.0),
        "horizon_volatility": safe_float(horizon_volatility, 0.0),
        "horizon_max_drawdown": safe_float(horizon_max_drawdown, 0.0),
        "horizon_range_pct": safe_float(horizon_range_pct, 0.0),
        "horizon_trend_slope": safe_float(horizon_trend_slope, 0.0),
        "horizon_avg_volume": safe_float(horizon_avg_volume, 0.0),
        "horizon_volume_ratio": safe_float(horizon_volume_ratio, 1.0),
        "horizon_window_bars": int(lookback),
    }
