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


from src.ml.feature_store_modules import (
    NUMERIC_TYPES as _NUMERIC_TYPES,
    compute_dist_to_liquidation,
    compute_horizon_features,
    compute_pandas_ta_indicators as _compute_pandas_ta_indicators,
    normalize_feature_vector,
    safe_float as _safe_float,
    symbol_aliases as _symbol_aliases,
    symbol_base as _symbol_base,
)


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
