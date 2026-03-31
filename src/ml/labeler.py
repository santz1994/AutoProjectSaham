"""Create labeled dataset by sliding-window over historical price series.

Produces a CSV dataset with simple technical features and a binary label:
label=1 when future return over `horizon` days > `threshold`, otherwise 0.
"""
from __future__ import annotations

import glob
import json
import os

import numpy as np
import pandas as pd


def _compute_features_for_index(arr: np.ndarray, t: int, short: int, long: int):
    n = len(arr)
    # ensure t is valid index
    if t < 0 or t >= n:
        raise IndexError("invalid index")

    # short SMA
    s_start = max(0, t + 1 - short)
    short_sma = float(arr[s_start : t + 1].mean())
    l_start = max(0, t + 1 - long)
    long_sma = float(arr[l_start : t + 1].mean())

    # returns
    rets = arr[1 : t + 1] / arr[:t] - 1.0 if t >= 1 else np.array([])
    vol = float(rets[-long:].std()) if len(rets) >= 1 else 0.0

    momentum = float(arr[t] / arr[s_start] - 1.0) if (t - s_start) >= 1 else 0.0

    return {
        "last_price": float(arr[t]),
        "short_sma": short_sma,
        "long_sma": long_sma,
        "volatility": vol,
        "momentum": momentum,
        "n_obs": int(t + 1),
    }


def build_dataset(
    price_dir: str = "data/prices",
    out_csv: str = "data/dataset/dataset.csv",
    short: int = 5,
    long: int = 20,
    horizon: int = 5,
    threshold: float = 0.02,
    max_symbols: int | None = None,
) -> str:
    os.makedirs(os.path.dirname(out_csv), exist_ok=True)
    files = glob.glob(os.path.join(price_dir, "*.json"))
    rows = []
    count = 0
    for f in files:
        if max_symbols is not None and count >= max_symbols:
            break
        try:
            with open(f, "r", encoding="utf-8") as fh:
                payload = json.load(fh)
            sym = payload.get("symbol") or os.path.splitext(os.path.basename(f))[0]
            prices = payload.get("prices") or payload.get("price") or []
            if not prices or len(prices) < (long + horizon + 1):
                continue
            arr = np.array(prices, dtype=float)

            # sliding window: t indexes the observation time
            # (we need t+horizon in range)
            for t in range(long, len(arr) - horizon):
                feats = _compute_features_for_index(arr, t, short, long)
                future_return = float(arr[t + horizon] / arr[t] - 1.0)
                label = 1 if future_return > threshold else 0
                row = {
                    "symbol": sym,
                    "t_index": int(t),
                    "future_return": future_return,
                    "label": int(label),
                }
                row.update(feats)
                rows.append(row)

            count += 1
        except Exception:
            continue

    if not rows:
        raise RuntimeError("No dataset rows produced (check price files)")

    df = pd.DataFrame(rows)
    df.to_csv(out_csv, index=False)
    return out_csv


if __name__ == "__main__":
    print("Building dataset...")
    out = build_dataset()
    print("Wrote dataset to", out)
