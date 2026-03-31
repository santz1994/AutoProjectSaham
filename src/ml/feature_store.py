"""Feature store utilities: compute technical indicators from price series.

This module computes a snapshot of numeric features per-symbol suitable for
baseline models and more advanced pipelines (SMA, volatility, momentum,
RSI, MACD, Bollinger Bands). It expects per-symbol JSON files saved by
`BatchFetcher` in `data/prices/*.json` containing a `prices` list.
"""
from __future__ import annotations

import glob
import json
import os
from typing import Dict, List, Optional

import pandas as pd


def _safe_rolling(series: pd.Series, window: int):
    if len(series) < window:
        return series.rolling(len(series))
    return series.rolling(window)


def compute_latest_features(
    prices: List[float],
    volumes: Optional[List[float]] = None,
    short: int = 5,
    long: int = 20,
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

    return {
        'last_price': last_price,
        'short_sma': float(short_sma),
        'long_sma': float(long_sma),
        'sma_ratio': sma_ratio,
        'volatility': float(volatility),
        'momentum': float(momentum),
        'n_obs': int(n),
        'avg_vol_5': float(avg_vol_5),
        'rsi_14': float(rsi),
        'macd': float(macd),
        'macd_signal': float(macd_signal),
        'bb_upper': float(bb_upper),
        'bb_lower': float(bb_lower),
        'bb_width': float(bb_width),
    }


def build_feature_snapshot(
    price_dir: str = 'data/prices',
    out_csv: str = 'data/features/features.csv',
    short: int = 5,
    long: int = 20,
) -> str:
    os.makedirs(os.path.dirname(out_csv), exist_ok=True)
    rows = []
    pattern = os.path.join(price_dir, '*.json')
    files = glob.glob(pattern)
    for fpath in files:
        try:
            with open(fpath, 'r', encoding='utf-8') as fh:
                payload = json.load(fh)
            sym = payload.get('symbol') or os.path.splitext(os.path.basename(fpath))[0]
            prices = (
                payload.get('prices')
                or payload.get('price')
                or payload.get('prices_list')
                or []
            )
            volumes = (
                payload.get('volumes')
                or payload.get('volume')
                or payload.get('volumes_list')
                or None
            )
            if not prices:
                continue
            feats = compute_latest_features(prices, volumes=volumes, short=short, long=long)
            if not feats:
                continue
            row = {'symbol': sym}
            row.update(feats)
            rows.append(row)
        except Exception:
            continue

    if not rows:
        raise RuntimeError('No feature rows produced (no price files?)')

    df = pd.DataFrame(rows)
    df.to_csv(out_csv, index=False)
    return out_csv


if __name__ == '__main__':
    print('Building feature snapshot...')
    out = build_feature_snapshot()
    print('Wrote features to', out)
