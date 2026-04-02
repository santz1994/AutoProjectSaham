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
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

# Import microstructure features
try:
    from src.ml.microstructure import (
        compute_microstructure_features,
        MicrostructureAnalyzer
    )
    MICROSTRUCTURE_AVAILABLE = True
except ImportError:
    MICROSTRUCTURE_AVAILABLE = False
    compute_microstructure_features = None
    MicrostructureAnalyzer = None


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
        except Exception:
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
        except Exception:
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
    except Exception:
        macd = 0.0
        macd_signal = 0.0

    # Bollinger Bands on `long` window
    try:
        ma_long = _safe_rolling(s, long).mean().iloc[-1]
        std_long = _safe_rolling(s, long).std().iloc[-1]
        bb_upper = float(ma_long + 2.0 * (std_long if not pd.isna(std_long) else 0.0))
        bb_lower = float(ma_long - 2.0 * (std_long if not pd.isna(std_long) else 0.0))
        bb_width = float(bb_upper - bb_lower)
    except Exception:
        bb_upper = float(s.mean())
        bb_lower = float(s.mean())
        bb_width = 0.0

    sma_ratio = float(short_sma / long_sma) if long_sma != 0 else 1.0

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
    }
    
    # Add microstructure features if available
    if include_microstructure and MICROSTRUCTURE_AVAILABLE and volumes is not None:
        try:
            # Create temporary DataFrame for microstructure calculation
            # Estimate high/low from close (simplified)
            close_arr = np.array(prices)
            high_arr = close_arr * 1.005  # +0.5% estimate
            low_arr = close_arr * 0.995   # -0.5% estimate
            vol_arr = np.array(volumes)
            
            df_temp = pd.DataFrame({
                'high': high_arr,
                'low': low_arr,
                'close': close_arr,
                'volume': vol_arr
            })
            
            # Compute microstructure features
            df_micro = compute_microstructure_features(df_temp)
            
            # Extract latest values
            features['vwap'] = float(df_micro['vwap'].iloc[-1])
            features['vwap_deviation'] = float(df_micro['vwap_deviation'].iloc[-1])
            features['order_flow_imbalance'] = float(df_micro['order_flow_imbalance'].iloc[-1])
            features['price_impact'] = float(df_micro['price_impact'].iloc[-1])
            features['amihud_illiquidity'] = float(df_micro['amihud_illiquidity'].iloc[-1])
        except Exception as e:
            # Silently skip microstructure if fails
            pass
    
    return features


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
        except Exception:
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
