"""Feature store utilities: compute technical indicators from price series.

This module computes a snapshot of numeric features per-symbol suitable for
baseline models and more advanced pipelines (SMA, volatility, momentum,
RSI, MACD, Bollinger Bands).

Enhanced with market microstructure features (VWAP, order flow, price impact).
"""
from __future__ import annotations

import glob
import json
import os
from datetime import datetime
from functools import lru_cache
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd  # type: ignore[import-untyped]

# Import microstructure features
try:
    from src.ml.microstructure import compute_microstructure_features

    MICROSTRUCTURE_AVAILABLE = True
except ImportError:
    MICROSTRUCTURE_AVAILABLE = False
    compute_microstructure_features = None  # type: ignore[assignment]


_EPSILON = 1e-9
_NUMERIC_TYPES = (int, float, np.number)


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        casted = float(value)
    except (TypeError, ValueError):
        return float(default)
    if not np.isfinite(casted):
        return float(default)
    return float(casted)


def _clip_unit(value: float) -> float:
    return float(np.clip(_safe_float(value, 0.0), -1.0, 1.0))


def _symbol_base(symbol: str) -> str:
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


def _symbol_aliases(symbol: str) -> List[str]:
    normalized = str(symbol or "").strip().upper()
    if not normalized:
        return []

    aliases: List[str] = [normalized]
    base = _symbol_base(normalized)
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


def compute_dist_to_liquidation(
    current_price: float,
    entry_price: float,
    leverage: float = 10.0,
    maintenance_margin_rate: float = 0.005,
    side: str = "long",
) -> float:
    """Compute normalized distance from current price to liquidation level.

    Positive value means current price is still above (long) or below (short)
    the estimated liquidation threshold.
    """
    current = max(_safe_float(current_price, 0.0), _EPSILON)
    entry = max(_safe_float(entry_price, current), _EPSILON)
    lev = max(_safe_float(leverage, 10.0), 1.0)
    mmr = float(np.clip(_safe_float(maintenance_margin_rate, 0.005), 0.0, 0.99))
    side_normalized = str(side or "long").strip().lower()
    is_short = side_normalized in {"short", "sell"}

    if is_short:
        liquidation_price = entry * (1.0 + (1.0 / lev) - mmr)
        distance = (liquidation_price - current) / current
    else:
        liquidation_price = entry * (1.0 - (1.0 / lev) + mmr)
        distance = (current - liquidation_price) / current

    return _safe_float(distance, 0.0)


def normalize_feature_vector(features: Dict[str, Any]) -> Dict[str, float]:
    """Normalize numeric feature dictionary into bounded values [-1, 1]."""
    if not features:
        return {}

    last_price = max(_safe_float(features.get("last_price"), 1.0), _EPSILON)
    normalized: Dict[str, float] = {}

    for key, value in features.items():
        if not isinstance(value, _NUMERIC_TYPES):
            continue
        val = _safe_float(value)

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

        normalized[f"norm_{key}"] = _clip_unit(float(n_val))

    return normalized


def _compute_pandas_ta_indicators(
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
                indicators["rsi_14"] = _safe_float(clean_rsi.iloc[-1], 50.0)
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
                    indicators["macd"] = _safe_float(clean_macd.iloc[-1], 0.0)
            if signal_col is not None:
                clean_signal = macd_df[signal_col].dropna()
                if len(clean_signal) > 0:
                    indicators["macd_signal"] = _safe_float(clean_signal.iloc[-1], 0.0)
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
                    upper_value = _safe_float(clean_upper.iloc[-1], 0.0)
                    indicators["bb_upper"] = upper_value

            if lower_col is not None:
                clean_lower = bb_df[lower_col].dropna()
                if len(clean_lower) > 0:
                    lower_value = _safe_float(clean_lower.iloc[-1], 0.0)
                    indicators["bb_lower"] = lower_value

            if width_col is not None:
                clean_width = bb_df[width_col].dropna()
                if len(clean_width) > 0:
                    indicators["bb_width"] = _safe_float(clean_width.iloc[-1], 0.0)
            elif upper_value is not None and lower_value is not None:
                indicators["bb_width"] = _safe_float(upper_value - lower_value, 0.0)
    except (TypeError, ValueError, AttributeError):
        pass

    return indicators


def _safe_rolling(series: pd.Series, window: int):
    if len(series) < window:
        return series.rolling(len(series))
    return series.rolling(window)


def compute_latest_features(
    prices: List[float],
    volumes: Optional[List[float]] = None,
    short: int = 5,
    long: int = 20,
    include_microstructure: bool = True,
    entry_price: Optional[float] = None,
    leverage: float = 10.0,
    maintenance_margin_rate: float = 0.005,
    position_side: str = "long",
    include_normalized: bool = True,
) -> Dict:
    """Compute a set of technical indicators from a price series.

    Returns a dict with numeric features. Gracefully handles short series.
    """
    if not prices:
        return {}

    s = pd.Series(prices, dtype=float).dropna()
    n = len(s)
    if n < 2:
        return {}

    # basic SMAs
    short_sma = float(s.tail(short).mean()) if n >= short else float(s.mean())
    long_sma = float(s.tail(long).mean()) if n >= long else float(s.mean())

    # volatility: std of returns over long window (or available data)
    returns = s.pct_change().dropna()
    if len(returns) == 0:
        volatility = 0.0
    else:
        try:
            volatility = float(_safe_rolling(returns, long).std().iloc[-1])
        except (TypeError, ValueError, IndexError):
            volatility = float(returns.std())

    # momentum: pct change over `short` periods
    if n >= short + 1:
        momentum = float(s.iloc[-1] / s.iloc[-short] - 1.0)
    else:
        momentum = float(s.iloc[-1] / s.iloc[0] - 1.0)

    last_price = float(s.iloc[-1])

    # average 5-day volume
    avg_vol_5 = 0.0
    if volumes:
        try:
            v = pd.Series(volumes, dtype=float).dropna()
            if len(v) > 0:
                avg_vol_5 = float(v.tail(5).mean())
        except (TypeError, ValueError):
            avg_vol_5 = 0.0

    # RSI (default 14)
    rsi_period = min(14, max(2, n - 1))
    delta = s.diff().dropna()
    if len(delta) >= 1:
        gain = delta.clip(lower=0)
        loss = -delta.clip(upper=0)
        avg_gain = float(gain.tail(rsi_period).mean()) if len(gain) >= 1 else 0.0
        avg_loss = float(loss.tail(rsi_period).mean()) if len(loss) >= 1 else 0.0
        if avg_loss == 0.0:
            rsi = 100.0 if avg_gain > 0 else 50.0
        else:
            rs = avg_gain / avg_loss
            rsi = float(100.0 - (100.0 / (1.0 + rs)))
    else:
        rsi = 50.0

    # MACD (12,26,9) — fallback to smaller spans for short series
    span_fast = 12 if n >= 12 else max(3, n // 2)
    span_slow = 26 if n >= 26 else max(span_fast + 1, n - 1)
    try:
        ema_fast = s.ewm(span=span_fast, adjust=False).mean()
        ema_slow = s.ewm(span=span_slow, adjust=False).mean()
        macd_series = ema_fast - ema_slow
        macd = float(macd_series.iloc[-1])
        macd_signal = float(macd_series.ewm(span=9, adjust=False).mean().iloc[-1])
    except (TypeError, ValueError, IndexError, FloatingPointError):
        macd = 0.0
        macd_signal = 0.0

    # Bollinger Bands on `long` window
    try:
        ma_long = _safe_rolling(s, long).mean().iloc[-1]
        std_long = _safe_rolling(s, long).std().iloc[-1]
        bb_upper = float(ma_long + 2.0 * (std_long if not pd.isna(std_long) else 0.0))
        bb_lower = float(ma_long - 2.0 * (std_long if not pd.isna(std_long) else 0.0))
        bb_width = float(bb_upper - bb_lower)
    except (TypeError, ValueError, IndexError):
        bb_upper = float(s.mean())
        bb_lower = float(s.mean())
        bb_width = 0.0

    # Phase 2.2 requirement: prefer pandas-ta indicators if library is available.
    ta_indicators = _compute_pandas_ta_indicators(s, long_window=long)
    if ta_indicators:
        rsi = _safe_float(ta_indicators.get("rsi_14", rsi), rsi)
        macd = _safe_float(ta_indicators.get("macd", macd), macd)
        macd_signal = _safe_float(
            ta_indicators.get("macd_signal", macd_signal),
            macd_signal,
        )
        bb_upper = _safe_float(ta_indicators.get("bb_upper", bb_upper), bb_upper)
        bb_lower = _safe_float(ta_indicators.get("bb_lower", bb_lower), bb_lower)
        bb_width = _safe_float(ta_indicators.get("bb_width", bb_width), bb_width)

    sma_ratio = float(short_sma / long_sma) if long_sma != 0 else 1.0

    effective_entry = _safe_float(entry_price, last_price)
    if effective_entry <= 0:
        effective_entry = last_price
    dist_to_liquidation = compute_dist_to_liquidation(
        current_price=last_price,
        entry_price=effective_entry,
        leverage=leverage,
        maintenance_margin_rate=maintenance_margin_rate,
        side=position_side,
    )

    features = {
        "last_price": last_price,
        "short_sma": float(short_sma),
        "long_sma": float(long_sma),
        "sma_ratio": sma_ratio,
        "volatility": float(volatility),
        "momentum": float(momentum),
        "n_obs": int(n),
        "avg_vol_5": float(avg_vol_5),
        "rsi_14": float(rsi),
        "macd": float(macd),
        "macd_signal": float(macd_signal),
        "bb_upper": float(bb_upper),
        "bb_lower": float(bb_lower),
        "bb_width": float(bb_width),
        "dist_to_liquidation": float(dist_to_liquidation),
    }

    # Add microstructure features if available
    if include_microstructure and MICROSTRUCTURE_AVAILABLE and volumes is not None:
        try:
            # Create temporary DataFrame for microstructure calculation
            # Estimate high/low from close (simplified)
            close_arr = np.array(prices)
            high_arr = close_arr * 1.005  # +0.5% estimate
            low_arr = close_arr * 0.995  # -0.5% estimate
            vol_arr = np.array(volumes)

            df_temp = pd.DataFrame(
                {
                    "high": high_arr,
                    "low": low_arr,
                    "close": close_arr,
                    "volume": vol_arr,
                }
            )

            # Compute microstructure features
            if compute_microstructure_features is None:
                return features
            df_micro = compute_microstructure_features(df_temp)

            # Extract latest values
            features["vwap"] = float(df_micro["vwap"].iloc[-1])
            features["vwap_deviation"] = float(df_micro["vwap_deviation"].iloc[-1])
            features["order_flow_imbalance"] = float(
                df_micro["order_flow_imbalance"].iloc[-1]
            )
            features["price_impact"] = float(df_micro["price_impact"].iloc[-1])
            features["amihud_illiquidity"] = float(
                df_micro["amihud_illiquidity"].iloc[-1]
            )
        except (TypeError, ValueError, KeyError, IndexError):
            # Silently skip microstructure if fails
            pass

    # Safety guard: remove NaN/Inf from all numeric feature values.
    for key, value in list(features.items()):
        if isinstance(value, _NUMERIC_TYPES):
            features[key] = _safe_float(value, 0.0)

    if include_normalized:
        features.update(normalize_feature_vector(features))

    return features


def compute_horizon_features(
    prices: List[float],
    volumes: Optional[List[float]] = None,
    horizon_bars: int = 5,
) -> Dict[str, float]:
    """Compute horizon-aware features for a configurable prediction window.

    These features explicitly encode short/medium/long behavior for the target
    horizon and help the model adapt across regimes.
    """
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
        "horizon_return": _safe_float(horizon_return, 0.0),
        "horizon_volatility": _safe_float(horizon_volatility, 0.0),
        "horizon_max_drawdown": _safe_float(horizon_max_drawdown, 0.0),
        "horizon_range_pct": _safe_float(horizon_range_pct, 0.0),
        "horizon_trend_slope": _safe_float(horizon_trend_slope, 0.0),
        "horizon_avg_volume": _safe_float(horizon_avg_volume, 0.0),
        "horizon_volume_ratio": _safe_float(horizon_volume_ratio, 1.0),
        "horizon_window_bars": int(lookback),
    }


def build_multimodal_feature_row(
    symbol: str,
    prices: List[float],
    volumes: Optional[List[float]] = None,
    *,
    sentiment_features: Optional[Dict[str, Any]] = None,
    cot_payload: Optional[Dict[str, Any]] = None,
    horizon: str = "intraday",
    horizon_bars: int = 5,
) -> Dict[str, Any]:
    """Build a single multimodal feature row for model training/inference.

    Combines:
    - Base price/volume technical + microstructure features
    - Optional sentiment features (precomputed from news pipeline)
    - Optional COT macro features (weekly positioning)

    The function is intentionally permissive and best-effort for optional
    modalities to keep ETL robust under partial data availability.
    """
    base = compute_latest_features(
        prices=prices,
        volumes=volumes,
        include_microstructure=True,
    )
    if not base:
        return {}

    row: Dict[str, Any] = {
        "symbol": str(symbol),
        "horizon": str(horizon),
        "horizon_bars": int(horizon_bars),
    }
    row.update(base)
    row.update(
        compute_horizon_features(
            prices=prices,
            volumes=volumes,
            horizon_bars=horizon_bars,
        )
    )

    # Sentiment inputs are already feature-like, keep numeric fields only.
    sentiment = sentiment_features or {}
    for key, value in sentiment.items():
        if isinstance(value, (int, float, np.number)):
            row[str(key)] = float(value)
    row["has_sentiment_features"] = int(any(k in row for k in sentiment.keys()))

    # COT payload can be either a direct snapshot or ETL-style payload with
    # nested latest record.
    cot_snapshot: Dict[str, Any] = {}
    if isinstance(cot_payload, dict):
        if isinstance(cot_payload.get("latest"), dict):
            cot_snapshot = cot_payload.get("latest", {}) or {}
        else:
            cot_snapshot = cot_payload

    cot_fields = {
        "cot_index_noncommercial": "cot_index_noncommercial",
        "cot_index_commercial": "cot_index_commercial",
        "noncommercial_net": "cot_noncommercial_net",
        "commercial_net": "cot_commercial_net",
    }

    cot_present = False
    for source_key, target_key in cot_fields.items():
        value = cot_snapshot.get(source_key)
        if isinstance(value, (int, float, np.number)):
            row[target_key] = float(value)
            cot_present = True

    if (
        "cot_index_noncommercial" in row
        and "cot_index_commercial" in row
    ):
        row["cot_index_spread"] = (
            row["cot_index_noncommercial"] - row["cot_index_commercial"]
        )

    row["has_cot_features"] = int(cot_present)

    for key, value in list(row.items()):
        if isinstance(value, _NUMERIC_TYPES):
            row[key] = _safe_float(value, 0.0)

    row.update(normalize_feature_vector(row))

    return row


def infer_horizon_tag(horizon_bars: int) -> str:
    """Convert numeric horizon bars into a coarse horizon category."""
    bars = int(horizon_bars)
    if bars <= 2:
        return "ultra_short"
    if bars <= 10:
        return "short_term"
    if bars <= 30:
        return "medium_term"
    return "long_term"


def _load_latest_etl_context(etl_dir: str = "data") -> Dict[str, Any]:
    """Load latest ETL artifact and return lightweight multimodal context."""
    pattern = os.path.join(etl_dir, "etl_*.json")
    files = glob.glob(pattern)
    if not files:
        return {"articles": [], "cot": {}}

    latest_file = max(files, key=os.path.getmtime)
    try:
        with open(latest_file, "r", encoding="utf-8") as file:
            payload = json.load(file)
    except (OSError, json.JSONDecodeError):
        return {"articles": [], "cot": {}}

    data = payload.get("data", payload) if isinstance(payload, dict) else {}
    if not isinstance(data, dict):
        return {"articles": [], "cot": {}}

    news_payload = data.get("news", {})
    if isinstance(news_payload, dict):
        articles = news_payload.get("articles", [])
    else:
        articles = []

    cot_payload = data.get("cot", {})
    if not isinstance(cot_payload, dict):
        cot_payload = {}

    return {
        "articles": articles if isinstance(articles, list) else [],
        "cot": cot_payload,
    }


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


@lru_cache(maxsize=8)
def _get_news_feature_extractor(
    use_finbert: bool,
    finbert_model: str,
    finbert_device: int,
):
    from src.ml.sentiment_features import NewsFeatureExtractor, SentimentAnalyzer

    analyzer = SentimentAnalyzer(
        use_vader=True,
        use_finbert=bool(use_finbert),
        finbert_model=finbert_model,
        device=int(finbert_device),
    )
    return NewsFeatureExtractor(sentiment_analyzer=analyzer)


def _compute_symbol_sentiment_features(
    symbol: str,
    articles: List[Dict[str, Any]],
    *,
    use_finbert: Optional[bool] = None,
    finbert_model: str = "ProsusAI/finbert",
    finbert_device: int = -1,
) -> Dict[str, Any]:
    """Best-effort sentiment features for one symbol from news articles."""
    if not articles:
        return {}

    if use_finbert is None:
        use_finbert = _env_bool("SENTIMENT_USE_FINBERT", default=False)

    model_name = os.getenv("SENTIMENT_FINBERT_MODEL", finbert_model)
    try:
        device = int(os.getenv("SENTIMENT_FINBERT_DEVICE", str(finbert_device)))
    except (TypeError, ValueError):
        device = int(finbert_device)

    try:
        extractor = _get_news_feature_extractor(
            bool(use_finbert),
            model_name,
            device,
        )
    except (RuntimeError, ImportError):
        return {}

    base_symbol = _symbol_base(symbol)
    try:
        return extractor.extract_features(
            articles=articles,
            symbol=base_symbol,
            current_date=datetime.utcnow(),
            windows=[1, 7, 30],
        )
    except (TypeError, ValueError):
        return {}


def _load_price_payload_by_symbol(
    price_dir: str,
    symbol: str,
) -> Optional[Dict[str, Any]]:
    """Resolve a symbol to a price JSON payload from `price_dir`."""
    candidates: List[str] = []
    for alias in _symbol_aliases(symbol):
        candidate = os.path.join(price_dir, f"{alias}.json")
        if candidate not in candidates:
            candidates.append(candidate)

    for path in candidates:
        if not os.path.exists(path):
            continue
        try:
            with open(path, "r", encoding="utf-8") as file:
                payload = json.load(file)
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(payload, dict):
            return payload

    target_base = _symbol_base(symbol)
    for path in glob.glob(os.path.join(price_dir, "*.json")):
        try:
            with open(path, "r", encoding="utf-8") as file:
                payload = json.load(file)
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(payload, dict):
            continue

        payload_symbol = payload.get("symbol") or os.path.splitext(
            os.path.basename(path)
        )[0]
        if _symbol_base(str(payload_symbol)) == target_base:
            return payload

    return None


def augment_dataset_with_multimodal(
    df: pd.DataFrame,
    *,
    price_dir: str = "data/prices",
    etl_dir: str = "data",
    horizon_bars: int = 5,
    use_finbert: Optional[bool] = None,
    finbert_model: str = "ProsusAI/finbert",
    finbert_device: int = -1,
) -> pd.DataFrame:
    """Augment an existing labeled dataset with multimodal feature columns.

    This function is safe-by-default and returns the original dataframe when
    modality sources are missing.
    """
    if df is None or len(df) == 0 or "symbol" not in df.columns:
        return df

    out_df = df.copy()
    horizon_tag = infer_horizon_tag(horizon_bars)
    etl_context = _load_latest_etl_context(etl_dir=etl_dir)
    articles = etl_context.get("articles", [])
    cot_payload = etl_context.get("cot", {})

    symbol_features: Dict[str, Dict[str, Any]] = {}
    unique_symbols = [str(item) for item in out_df["symbol"].dropna().unique().tolist()]

    for symbol in unique_symbols:
        payload = _load_price_payload_by_symbol(price_dir=price_dir, symbol=symbol)
        if not payload:
            continue

        prices = payload.get("prices") or payload.get("price") or []
        volumes = payload.get("volumes") or payload.get("volume") or None
        if not isinstance(prices, list) or len(prices) < 2:
            continue
        if volumes is not None and not isinstance(volumes, list):
            volumes = None

        sentiment_features = _compute_symbol_sentiment_features(
            symbol=symbol,
            articles=articles,
            use_finbert=use_finbert,
            finbert_model=finbert_model,
            finbert_device=finbert_device,
        )
        multimodal = build_multimodal_feature_row(
            symbol=symbol,
            prices=prices,
            volumes=volumes,
            sentiment_features=sentiment_features,
            cot_payload=cot_payload,
            horizon=horizon_tag,
            horizon_bars=horizon_bars,
        )
        if not multimodal:
            continue

        for alias in _symbol_aliases(symbol):
            symbol_features[alias] = multimodal

    if symbol_features:
        per_row = []
        for value in out_df["symbol"].tolist():
            resolved: Dict[str, Any] = {}
            for alias in _symbol_aliases(str(value)):
                if alias in symbol_features:
                    resolved = symbol_features[alias]
                    break
            per_row.append(resolved)

        features_df = pd.DataFrame(per_row, index=out_df.index)
        if (
            "horizon" in features_df.columns
            and "horizon_tag" not in features_df.columns
        ):
            features_df = features_df.rename(columns={"horizon": "horizon_tag"})

        for col in features_df.columns:
            if col == "symbol":
                continue
            if col in out_df.columns:
                if out_df[col].isna().any():
                    out_df[col] = out_df[col].where(
                        out_df[col].notna(),
                        features_df[col],
                    )
                continue
            out_df[col] = features_df[col]

    if "horizon_tag" not in out_df.columns:
        out_df["horizon_tag"] = horizon_tag
    if "horizon_bars" not in out_df.columns:
        out_df["horizon_bars"] = int(horizon_bars)

    return out_df


def build_feature_snapshot(
    price_dir: str = "data/prices",
    out_csv: str = "data/features/features.csv",
    short: int = 5,
    long: int = 20,
) -> str:
    os.makedirs(os.path.dirname(out_csv), exist_ok=True)
    rows = []
    pattern = os.path.join(price_dir, "*.json")
    files = glob.glob(pattern)
    for fpath in files:
        try:
            with open(fpath, "r", encoding="utf-8") as fh:
                payload = json.load(fh)
            sym = payload.get("symbol") or os.path.splitext(os.path.basename(fpath))[0]
            prices = (
                payload.get("prices")
                or payload.get("price")
                or payload.get("prices_list")
                or []
            )
            volumes = (
                payload.get("volumes")
                or payload.get("volume")
                or payload.get("volumes_list")
                or None
            )
            if not prices:
                continue
            feats = compute_latest_features(
                prices, volumes=volumes, short=short, long=long
            )
            if not feats:
                continue
            row = {"symbol": sym}
            row.update(feats)
            rows.append(row)
        except (OSError, json.JSONDecodeError, TypeError, ValueError, KeyError):
            continue

    if not rows:
        raise RuntimeError("No feature rows produced (no price files?)")

    df = pd.DataFrame(rows)
    df.to_csv(out_csv, index=False)
    return out_csv


def calculate_idx_microstructure_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Kalkulasi fitur mikrostruktur pasar spesifik BEI.

    Membutuhkan kolom tambahan bila tersedia: 'foreign_buy', 'foreign_sell',
    'bid_vol', 'offer_vol', dan 'volume'. Fungsi ini menambah beberapa fitur
    penting: net foreign flow, VWAP, price-to-VWAP ratio, dan order-book imbalance.
    """
    df = df.copy()

    # 1. Net Foreign Flow Momentum
    if "foreign_buy" in df.columns and "foreign_sell" in df.columns:
        df["net_foreign"] = df["foreign_buy"] - df["foreign_sell"]
        df["foreign_flow_ma5"] = df["net_foreign"].rolling(window=5).mean()
        # Normalisasi terhadap total volume (hindari pembagian nol)
        if "volume" in df.columns:
            denom = (df["volume"] * 2).replace(0, np.nan)
            df["foreign_participation"] = (
                (df["foreign_buy"].fillna(0) + df["foreign_sell"].fillna(0)) / denom
            ).fillna(0.0)

    # 2. VWAP dan rasio harga terhadap VWAP
    if "typical_price" not in df.columns:
        if set(["high", "low", "close"]).issubset(df.columns):
            df["typical_price"] = (df["high"] + df["low"] + df["close"]) / 3.0
        else:
            df["typical_price"] = df.get("close", pd.Series(dtype=float))

    if "volume" in df.columns:
        df["cum_vol_price"] = (df["typical_price"] * df["volume"]).cumsum()
        df["cum_vol"] = df["volume"].cumsum()
        df["vwap"] = df["cum_vol_price"] / df["cum_vol"].replace({0: np.nan})
        df["vwap"] = (
            df["vwap"]
            .ffill()
            .fillna(df.get("close", df["typical_price"]))
        )
        # price to vwap ratio
        if "close" in df.columns:
            df["price_to_vwap_ratio"] = df["close"] / df["vwap"].replace({0: np.nan})
        else:
            df["price_to_vwap_ratio"] = np.nan

    # 3. Order Book Imbalance
    if "bid_vol" in df.columns and "offer_vol" in df.columns:
        denom = (df["bid_vol"] + df["offer_vol"]).replace(0, np.nan)
        df["order_book_imbalance"] = (df["bid_vol"] / denom).fillna(0.5)

    return df


if __name__ == "__main__":
    print("Building feature snapshot...")
    out = build_feature_snapshot()
    print("Wrote features to", out)
