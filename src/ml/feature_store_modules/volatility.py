"""Volatility/indicator helper functions for feature-store pipeline."""

from __future__ import annotations

from typing import Dict

import pandas as pd  # type: ignore[import-untyped]

from .core_store import safe_float


def compute_pandas_ta_indicators(
    close_series: pd.Series,
    long_window: int,
) -> Dict[str, float]:
    """Compute RSI, MACD, and Bollinger metrics via pandas-ta when available."""
    try:
        import pandas_ta as ta  # type: ignore
    except ImportError:
        return {}

    indicators: Dict[str, float] = {}
    close = close_series.astype(float)

    try:
        rsi_series = ta.rsi(close, length=14)
        if isinstance(rsi_series, pd.Series):
            clean_rsi = rsi_series.dropna()
            if len(clean_rsi) > 0:
                indicators["rsi_14"] = safe_float(clean_rsi.iloc[-1], 50.0)
    except (TypeError, ValueError, AttributeError):
        pass

    try:
        macd_df = ta.macd(close, fast=12, slow=26, signal=9)
        if isinstance(macd_df, pd.DataFrame) and len(macd_df) > 0:
            macd_col = next(
                (col for col in macd_df.columns if str(col).startswith("MACD_")),
                None,
            )
            signal_col = next(
                (col for col in macd_df.columns if str(col).startswith("MACDs_")),
                None,
            )
            if macd_col is not None:
                clean_macd = macd_df[macd_col].dropna()
                if len(clean_macd) > 0:
                    indicators["macd"] = safe_float(clean_macd.iloc[-1], 0.0)
            if signal_col is not None:
                clean_signal = macd_df[signal_col].dropna()
                if len(clean_signal) > 0:
                    indicators["macd_signal"] = safe_float(clean_signal.iloc[-1], 0.0)
    except (TypeError, ValueError, AttributeError):
        pass

    try:
        bb_length = min(20, max(5, int(long_window)))
        bb_df = ta.bbands(close, length=bb_length)  # type: ignore[arg-type]
        if isinstance(bb_df, pd.DataFrame) and len(bb_df) > 0:
            upper_col = next(
                (col for col in bb_df.columns if str(col).startswith("BBU_")),
                None,
            )
            lower_col = next(
                (col for col in bb_df.columns if str(col).startswith("BBL_")),
                None,
            )
            width_col = next(
                (col for col in bb_df.columns if str(col).startswith("BBB_")),
                None,
            )

            upper_value = None
            lower_value = None

            if upper_col is not None:
                clean_upper = bb_df[upper_col].dropna()
                if len(clean_upper) > 0:
                    upper_value = safe_float(clean_upper.iloc[-1], 0.0)
                    indicators["bb_upper"] = upper_value

            if lower_col is not None:
                clean_lower = bb_df[lower_col].dropna()
                if len(clean_lower) > 0:
                    lower_value = safe_float(clean_lower.iloc[-1], 0.0)
                    indicators["bb_lower"] = lower_value

            if width_col is not None:
                clean_width = bb_df[width_col].dropna()
                if len(clean_width) > 0:
                    indicators["bb_width"] = safe_float(clean_width.iloc[-1], 0.0)
            elif upper_value is not None and lower_value is not None:
                indicators["bb_width"] = safe_float(upper_value - lower_value, 0.0)
    except (TypeError, ValueError, AttributeError):
        pass

    return indicators
