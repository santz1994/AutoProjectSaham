"""Feature store utilities: compute simple technical features from price series.

This module computes a snapshot of numeric features per-symbol suitable for
baseline models (SMA, volatility, momentum). It expects per-symbol JSON files
saved by `BatchFetcher` in `data/prices/*.json` containing a `prices` list.
"""
from __future__ import annotations

import glob
import json
import os
from typing import Dict, List, Optional

import numpy as np
import pandas as pd


def compute_latest_features(prices: List[float], volumes: Optional[List[float]] = None, short: int = 5, long: int = 20) -> Dict:
        """Compute a small set of technical features from a price series.

        - `prices` is a list of floats (most callers pass the `prices` array).
        - `volumes` is optional and, if provided, is used to compute a 5-day
            average volume feature useful for liquidity estimation.
        """

        arr = np.array(prices, dtype=float)
    n = len(arr)
    if n < 2:
        return {}

    # returns (n-1)
    rets = arr[1:] / arr[:-1] - 1.0

    short_sma = float(arr[-short:].mean()) if n >= short else float(arr.mean())
    long_sma = float(arr[-long:].mean()) if n >= long else float(arr.mean())
    vol = float(rets[-long:].std()) if len(rets) >= long else float(rets.std()) if len(rets) > 0 else 0.0
    momentum = float(arr[-1] / arr[-short] - 1.0) if n >= short else float(arr[-1] / arr[0] - 1.0)
    last_price = float(arr[-1])

    # optional 5-day average volume (liquidity signal)
    avg_vol_5 = 0.0
    if volumes:
        try:
            v = np.array(volumes, dtype=float)
            if len(v) >= 1:
                avg_vol_5 = float(np.mean(v[-5:])) if len(v) >= 5 else float(np.mean(v))
        except Exception:
            avg_vol_5 = 0.0

    return {
        'last_price': last_price,
        'short_sma': short_sma,
        'long_sma': long_sma,
        'volatility': vol,
        'momentum': momentum,
        'n_obs': n,
        'avg_vol_5': avg_vol_5,
    }


def build_feature_snapshot(price_dir: str = 'data/prices', out_csv: str = 'data/features/features.csv', short: int = 5, long: int = 20) -> str:
    os.makedirs(os.path.dirname(out_csv), exist_ok=True)
    rows = []
    pattern = os.path.join(price_dir, '*.json')
    files = glob.glob(pattern)
    for fpath in files:
        try:
            with open(fpath, 'r', encoding='utf-8') as fh:
                payload = json.load(fh)
            sym = payload.get('symbol') or os.path.splitext(os.path.basename(fpath))[0]
            prices = payload.get('prices') or payload.get('price') or payload.get('prices_list') or []
            volumes = payload.get('volumes') or payload.get('volume') or payload.get('volumes_list') or None
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
