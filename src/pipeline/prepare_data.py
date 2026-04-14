"""Prepare high-frequency OHLCV data into a feature-rich training dataset.

Phase 2.3 pipeline:
- Fetch or load raw OHLCV candles
- Compute technical, horizon, liquidation, and microstructure features
- Normalize features and enforce NaN/Inf safety checks
- Save clean dataset ready for downstream model training
"""

from __future__ import annotations

import os
from typing import Any, Dict, Optional, Sequence

import numpy as np
import pandas as pd  # type: ignore[import-untyped]

from src.ml.feature_store import infer_horizon_tag, normalize_feature_vector
from src.pipeline.data_connectors.hf_connector import fetch_historical_data

try:
    from src.ml.microstructure import compute_microstructure_features
except ImportError:
    compute_microstructure_features = None  # type: ignore[assignment]


_REQUIRED_OHLCV_COLUMNS = ("open", "high", "low", "close", "volume")
_DEFAULT_REQUIRED_FEATURE_COLUMNS = (
    "symbol",
    "timeframe",
    "timestamp",
    "datetime",
    "last_price",
    "rsi_14",
    "macd",
    "bb_width",
    "dist_to_liquidation",
    "norm_rsi_14",
    "norm_macd",
    "norm_bb_width",
    "norm_dist_to_liquidation",
)


def _rolling_slope(values: np.ndarray) -> float:
    """Compute linear trend slope over a rolling window."""
    if values is None or len(values) <= 1:
        return 0.0

    x_axis = np.arange(len(values), dtype=float)
    y_axis = np.asarray(values, dtype=float)

    x_centered = x_axis - x_axis.mean()
    denom = float(np.dot(x_centered, x_centered))
    if denom == 0.0:
        return 0.0

    y_centered = y_axis - y_axis.mean()
    return float(np.dot(x_centered, y_centered) / denom)


def _ensure_datetime_columns(raw_df: pd.DataFrame) -> pd.DataFrame:
    """Ensure raw DataFrame has both `timestamp` (ms) and `datetime` (UTC)."""
    df = raw_df.copy()

    if "datetime" not in df.columns and "timestamp" not in df.columns:
        raise ValueError("raw OHLCV data must contain `timestamp` or `datetime`")

    if "datetime" not in df.columns:
        df["datetime"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
    else:
        df["datetime"] = pd.to_datetime(df["datetime"], utc=True, errors="coerce")

    if "timestamp" not in df.columns:
        dt_ns = df["datetime"].astype("int64")
        df["timestamp"] = (dt_ns // 1_000_000).astype("int64")

    df["timestamp"] = pd.to_numeric(df["timestamp"], errors="coerce").astype("Int64")

    if df["datetime"].isna().any() or df["timestamp"].isna().any():
        raise ValueError("raw OHLCV contains invalid datetime/timestamp values")

    df["timestamp"] = df["timestamp"].astype("int64")
    return df


def _normalize_numeric_features(features_df: pd.DataFrame) -> pd.DataFrame:
    """Apply feature-store normalization row-by-row to produce norm_* columns."""
    normalized_rows = [
        normalize_feature_vector(row)
        for row in features_df.to_dict(orient="records")
    ]
    normalized_df = pd.DataFrame(normalized_rows, index=features_df.index)
    return normalized_df.fillna(0.0)


def _write_dataset(df: pd.DataFrame, out_path: str) -> str:
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)

    if out_path.lower().endswith(".parquet"):
        df.to_parquet(out_path, index=False)
    else:
        df.to_csv(out_path, index=False)

    return out_path


def build_feature_dataset(
    raw_df: pd.DataFrame,
    *,
    symbol: str,
    timeframe: str,
    short_window: int = 5,
    long_window: int = 20,
    horizon_bars: int = 8,
    leverage: float = 20.0,
    maintenance_margin_rate: float = 0.005,
    position_side: str = "long",
    include_microstructure: bool = True,
    dropna: bool = True,
) -> pd.DataFrame:
    """Build a clean feature dataset from OHLCV candles."""
    if raw_df is None or len(raw_df) == 0:
        raise ValueError("raw_df cannot be empty")

    work = _ensure_datetime_columns(raw_df)

    for column in _REQUIRED_OHLCV_COLUMNS:
        if column not in work.columns:
            raise ValueError(f"raw OHLCV missing required column: {column}")
        work[column] = pd.to_numeric(work[column], errors="coerce")

    work = work.sort_values("timestamp").drop_duplicates(
        subset=["timestamp"],
        keep="last",
    )
    work = work.reset_index(drop=True)

    close = work["close"].astype(float)
    volume = work["volume"].astype(float)
    returns = close.pct_change()

    short_window = max(2, int(short_window))
    long_window = max(short_window + 1, int(long_window))
    horizon_bars = max(1, int(horizon_bars))

    features = pd.DataFrame(index=work.index)
    features["last_price"] = close
    features["short_sma"] = close.rolling(short_window, min_periods=short_window).mean()
    features["long_sma"] = close.rolling(long_window, min_periods=long_window).mean()
    features["sma_ratio"] = features["short_sma"] / features["long_sma"]
    features["volatility"] = returns.rolling(long_window, min_periods=long_window).std()
    features["momentum"] = close / close.shift(short_window) - 1.0
    features["n_obs"] = np.arange(1, len(work) + 1, dtype=float)
    features["avg_vol_5"] = volume.rolling(5, min_periods=5).mean()

    delta = close.diff()
    gains = delta.clip(lower=0.0)
    losses = -delta.clip(upper=0.0)
    avg_gain = gains.rolling(14, min_periods=14).mean()
    avg_loss = losses.rolling(14, min_periods=14).mean()

    rs = avg_gain / avg_loss.replace(0.0, np.nan)
    rsi = 100.0 - (100.0 / (1.0 + rs))
    rsi = rsi.where(~((avg_loss == 0.0) & (avg_gain > 0.0)), 100.0)
    rsi = rsi.where(~((avg_loss == 0.0) & (avg_gain == 0.0)), 50.0)
    features["rsi_14"] = rsi.fillna(50.0)

    ema_fast = close.ewm(span=12, adjust=False).mean()
    ema_slow = close.ewm(span=26, adjust=False).mean()
    features["macd"] = ema_fast - ema_slow
    features["macd_signal"] = features["macd"].ewm(span=9, adjust=False).mean()

    ma_long = close.rolling(long_window, min_periods=long_window).mean()
    std_long = close.rolling(long_window, min_periods=long_window).std()
    features["bb_upper"] = ma_long + (2.0 * std_long)
    features["bb_lower"] = ma_long - (2.0 * std_long)
    features["bb_width"] = features["bb_upper"] - features["bb_lower"]

    safe_close = close.replace(0.0, np.nan)
    effective_entry = close.shift(1).fillna(close)
    safe_leverage = max(float(leverage), 1.0)
    mmr = float(np.clip(float(maintenance_margin_rate), 0.0, 0.99))

    is_short = str(position_side or "long").strip().lower() in {"short", "sell"}
    if is_short:
        liquidation_price = effective_entry * (1.0 + (1.0 / safe_leverage) - mmr)
        features["dist_to_liquidation"] = (liquidation_price - close) / safe_close
    else:
        liquidation_price = effective_entry * (1.0 - (1.0 / safe_leverage) + mmr)
        features["dist_to_liquidation"] = (close - liquidation_price) / safe_close

    rolling_max = close.rolling(horizon_bars, min_periods=horizon_bars).max()
    rolling_min = close.rolling(horizon_bars, min_periods=horizon_bars).min()
    denom = close.shift(horizon_bars - 1).abs().replace(0.0, np.nan)

    features["horizon_return"] = close.pct_change(periods=horizon_bars)
    features["horizon_volatility"] = returns.rolling(
        horizon_bars,
        min_periods=horizon_bars,
    ).std()
    features["horizon_max_drawdown"] = (close / rolling_max) - 1.0
    features["horizon_range_pct"] = (rolling_max - rolling_min) / denom
    features["horizon_trend_slope"] = (
        close.rolling(horizon_bars, min_periods=horizon_bars)
        .apply(_rolling_slope, raw=True)
        / close.abs().replace(0.0, np.nan)
    )
    features["horizon_avg_volume"] = volume.rolling(
        horizon_bars,
        min_periods=horizon_bars,
    ).mean()
    baseline_volume = features["horizon_avg_volume"].shift(horizon_bars)
    features["horizon_volume_ratio"] = (
        features["horizon_avg_volume"] / baseline_volume.replace(0.0, np.nan)
    )
    features["horizon_window_bars"] = float(horizon_bars)

    if include_microstructure and compute_microstructure_features is not None:
        try:
            micro_df = compute_microstructure_features(
                work[["high", "low", "close", "volume"]].copy()
            )
            for column in (
                "vwap",
                "vwap_deviation",
                "order_flow_imbalance",
                "price_impact",
                "amihud_illiquidity",
            ):
                features[column] = pd.to_numeric(micro_df[column], errors="coerce")
        except (TypeError, ValueError, KeyError):
            # Continue without microstructure features when optional data fails.
            pass

    normalized = _normalize_numeric_features(
        features.select_dtypes(include=[np.number])
    )
    features = pd.concat([features, normalized], axis=1)

    features = features.replace([np.inf, -np.inf], np.nan)

    required_for_cleaning = [
        "last_price",
        "short_sma",
        "long_sma",
        "sma_ratio",
        "volatility",
        "momentum",
        "avg_vol_5",
        "rsi_14",
        "macd",
        "macd_signal",
        "bb_upper",
        "bb_lower",
        "bb_width",
        "dist_to_liquidation",
        "horizon_return",
        "horizon_volatility",
        "horizon_max_drawdown",
        "horizon_range_pct",
        "horizon_trend_slope",
        "horizon_avg_volume",
        "horizon_volume_ratio",
        "norm_rsi_14",
        "norm_macd",
        "norm_bb_width",
        "norm_dist_to_liquidation",
    ]

    for optional_column in (
        "vwap",
        "vwap_deviation",
        "order_flow_imbalance",
        "price_impact",
        "amihud_illiquidity",
    ):
        if optional_column in features.columns:
            required_for_cleaning.append(optional_column)

    if dropna:
        features = features.dropna(
            subset=[
                column
                for column in required_for_cleaning
                if column in features.columns
            ]
        )

    out = pd.DataFrame(index=work.index)
    out["symbol"] = str(symbol or "").strip().upper()
    out["timeframe"] = str(timeframe or "").strip()
    out["timestamp"] = work["timestamp"].astype("int64")
    out["datetime"] = pd.to_datetime(work["datetime"], utc=True)
    out["horizon_tag"] = infer_horizon_tag(horizon_bars)
    out["horizon_bars"] = int(horizon_bars)

    out = pd.concat([out, features], axis=1)
    out = out.loc[features.index].reset_index(drop=True)

    return out


def validate_feature_dataset(
    feature_df: pd.DataFrame,
    *,
    min_required_rows: int = 1_000,
    required_columns: Optional[Sequence[str]] = None,
) -> Dict[str, Any]:
    """Validate feature dataset for NaN/Inf safety and schema completeness."""
    if feature_df is None or len(feature_df) == 0:
        raise RuntimeError("feature dataset is empty")

    if min_required_rows > 0 and len(feature_df) < int(min_required_rows):
        raise RuntimeError(
            f"feature dataset too small: {len(feature_df)} < {int(min_required_rows)}"
        )

    required = tuple(required_columns or _DEFAULT_REQUIRED_FEATURE_COLUMNS)
    missing = [column for column in required if column not in feature_df.columns]
    if missing:
        raise RuntimeError(f"missing required feature columns: {missing}")

    numeric_df = feature_df.select_dtypes(include=[np.number])
    nan_counts = numeric_df.isna().sum()
    nan_columns = [
        column
        for column, count in nan_counts.items()
        if int(count) > 0
    ]
    if nan_columns:
        raise RuntimeError(f"NaN values detected in feature columns: {nan_columns}")

    if np.isinf(numeric_df.to_numpy(dtype=float)).any():
        raise RuntimeError("Inf values detected in numeric feature columns")

    if not pd.Series(feature_df["timestamp"]).is_monotonic_increasing:
        raise RuntimeError("timestamp column is not monotonic increasing")

    start_dt = pd.to_datetime(feature_df["datetime"].iloc[0], utc=True)
    end_dt = pd.to_datetime(feature_df["datetime"].iloc[-1], utc=True)

    return {
        "rows": int(len(feature_df)),
        "columns": list(feature_df.columns),
        "timestamp_start": start_dt.isoformat(),
        "timestamp_end": end_dt.isoformat(),
    }


def _load_raw_dataframe(input_csv: str) -> pd.DataFrame:
    if not os.path.exists(input_csv):
        raise FileNotFoundError(f"input_csv not found: {input_csv}")

    df = pd.read_csv(input_csv)
    if "datetime" in df.columns:
        df["datetime"] = pd.to_datetime(df["datetime"], utc=True, errors="coerce")
    return df


def prepare_training_dataset(
    *,
    exchange_id: str = "binance",
    symbol: str = "BTC/USDT",
    timeframe: str = "5m",
    candles: int = 100_000,
    batch_limit: int = 1_000,
    market_type: str = "spot",
    strict: bool = True,
    input_csv: Optional[str] = None,
    raw_out: Optional[str] = None,
    features_out: str = "data/dataset/hf_BTCUSDT_5m_features.csv",
    short_window: int = 5,
    long_window: int = 20,
    horizon_bars: int = 8,
    leverage: float = 20.0,
    maintenance_margin_rate: float = 0.005,
    position_side: str = "long",
    include_microstructure: bool = True,
    dropna: bool = True,
    min_required_rows: int = 1_000,
    max_rows: int = 0,
) -> Dict[str, Any]:
    """Execute full Phase 2.3 prepare-data pipeline and return summary."""
    if input_csv:
        raw_df = _load_raw_dataframe(input_csv)
    else:
        raw_df = fetch_historical_data(
            exchange_id=exchange_id,
            symbol=symbol,
            timeframe=timeframe,
            candles=candles,
            batch_limit=batch_limit,
            market_type=market_type,
            strict=strict,
        )

    if int(max_rows) > 0:
        raw_df = raw_df.tail(int(max_rows)).reset_index(drop=True)

    if raw_out:
        _write_dataset(raw_df, raw_out)

    feature_df = build_feature_dataset(
        raw_df,
        symbol=symbol,
        timeframe=timeframe,
        short_window=short_window,
        long_window=long_window,
        horizon_bars=horizon_bars,
        leverage=leverage,
        maintenance_margin_rate=maintenance_margin_rate,
        position_side=position_side,
        include_microstructure=include_microstructure,
        dropna=dropna,
    )

    summary = validate_feature_dataset(
        feature_df,
        min_required_rows=min_required_rows,
    )

    _write_dataset(feature_df, features_out)

    summary.update(
        {
            "symbol": str(symbol).upper(),
            "timeframe": timeframe,
            "raw_rows": int(len(raw_df)),
            "feature_rows": int(len(feature_df)),
            "features_out": features_out,
        }
    )
    if raw_out:
        summary["raw_out"] = raw_out
    if input_csv:
        summary["input_csv"] = input_csv

    return summary
