"""Create labeled dataset by sliding-window over historical price series.

Supports two labeling methods:
1. Simple threshold labeling (legacy): label=1 when future return > threshold
2. Triple-barrier labeling (recommended): considers take-profit, stop-loss, and time horizon

Triple-barrier method produces more realistic labels for trading strategies
by accounting for both profit targets and risk management.
"""
from __future__ import annotations

import glob
import json
import os

import numpy as np
import pandas as pd

from src.ml.barriers import (
    TripleBarrierLabeler,
    get_sample_weights_time_decay,
    get_sample_weights_by_return,
)
from src.ml.feature_store import augment_dataset_with_multimodal


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
    use_triple_barrier: bool = True,
    take_profit: float = 0.03,
    stop_loss: float = 0.02,
    use_sample_weights: bool = True,
    sample_weight_method: str = "time_decay",
    include_multimodal: bool = True,
    etl_dir: str = "data",
) -> str:
    """
    Build labeled dataset from price history.
    
    Args:
        price_dir: Directory containing price JSON files
        out_csv: Output CSV path
        short: Short SMA period
        long: Long SMA period
        horizon: Forward-looking horizon for labeling
        threshold: Return threshold for simple labeling
        max_symbols: Limit number of symbols (None = all)
        use_triple_barrier: If True, use triple-barrier labeling (recommended)
        take_profit: Take-profit threshold for triple-barrier (e.g., 0.03 = 3%)
        stop_loss: Stop-loss threshold for triple-barrier (e.g., 0.02 = 2%)
        use_sample_weights: If True, generate sample weights
        sample_weight_method: "time_decay" or "return_magnitude"
        include_multimodal: If True, merge sentiment + COT + horizon features
        etl_dir: Directory containing ETL artifacts (etl_*.json)
        
    Returns:
        Path to output CSV file
    """
    os.makedirs(os.path.dirname(out_csv), exist_ok=True)
    files = glob.glob(os.path.join(price_dir, "*.json"))
    rows = []
    count = 0
    
    # Initialize triple-barrier labeler if requested
    if use_triple_barrier:
        barrier_labeler = TripleBarrierLabeler(
            take_profit=take_profit,
            stop_loss=stop_loss,
            max_horizon=horizon
        )
    
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

            # Apply triple-barrier labeling if enabled
            if use_triple_barrier:
                try:
                    barrier_df = barrier_labeler.label_series(arr, min_observations=long)
                    
                    # Merge features with barrier labels
                    for _, barrier_row in barrier_df.iterrows():
                        try:
                            t = int(barrier_row['t_index'])
                        except (TypeError, ValueError):
                            continue
                        feats = _compute_features_for_index(arr, t, short, long)
                        
                        row = {
                            "symbol": sym,
                            "t_index": int(t),
                            "future_return": barrier_row['actual_return'],
                            "label": int(barrier_row['label']),
                            "bars_to_exit": int(barrier_row['bars_to_exit']),
                            "entry_price": float(barrier_row['entry_price']),
                        }
                        row.update(feats)
                        rows.append(row)
                except Exception as e:
                    # Fall back to simple labeling if triple-barrier fails
                    print(f"Warning: Triple-barrier failed for {sym}, using simple labeling: {e}")
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
            else:
                # Simple threshold labeling (legacy)
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

    # Optional multimodal feature augmentation (sentiment + COT + horizon tag)
    if include_multimodal:
        try:
            df = augment_dataset_with_multimodal(
                df,
                price_dir=price_dir,
                etl_dir=etl_dir,
                horizon_bars=horizon,
            )
        except Exception as e:
            print(f"Warning: multimodal augmentation skipped: {e}")
    
    # Add sample weights if requested
    if use_sample_weights and len(df) > 0:
        if sample_weight_method == "time_decay":
            weights = get_sample_weights_time_decay(len(df), decay_factor=0.95)
        elif sample_weight_method == "return_magnitude":
            weights = get_sample_weights_by_return(df['future_return'].values)
        else:
            raise ValueError(f"Unknown sample_weight_method: {sample_weight_method}")
        
        df['sample_weight'] = weights
    
    df.to_csv(out_csv, index=False)
    
    # Print summary statistics
    print(f"\n=== Dataset Summary ===")
    print(f"Total samples: {len(df)}")
    print(f"Unique symbols: {df['symbol'].nunique()}")
    if include_multimodal:
        sentiment_cov = 0.0
        cot_cov = 0.0
        if 'has_sentiment_features' in df.columns:
            sentiment_cov = float(df['has_sentiment_features'].mean() * 100)
        if 'has_cot_features' in df.columns:
            cot_cov = float(df['has_cot_features'].mean() * 100)
        print(
            "Multimodal coverage: "
            f"sentiment={sentiment_cov:.1f}% | cot={cot_cov:.1f}%"
        )
    if use_triple_barrier:
        print(f"\nLabel distribution (triple-barrier):")
        print(f"  Profit (1): {(df['label'] == 1).sum()} ({(df['label'] == 1).mean()*100:.1f}%)")
        print(f"  Loss (-1): {(df['label'] == -1).sum()} ({(df['label'] == -1).mean()*100:.1f}%)")
        print(f"  Neutral (0): {(df['label'] == 0).sum()} ({(df['label'] == 0).mean()*100:.1f}%)")
        if 'bars_to_exit' in df.columns:
            print(f"  Avg bars to exit: {df['bars_to_exit'].mean():.2f}")
    else:
        print(f"\nLabel distribution (simple threshold):")
        print(f"  Positive (1): {(df['label'] == 1).sum()} ({(df['label'] == 1).mean()*100:.1f}%)")
        print(f"  Negative (0): {(df['label'] == 0).sum()} ({(df['label'] == 0).mean()*100:.1f}%)")
    print(f"Avg future return: {df['future_return'].mean():.4f} ({df['future_return'].mean()*100:.2f}%)")
    print(f"Output: {out_csv}\n")
    
    return out_csv


if __name__ == "__main__":
    print("Building dataset...")
    out = build_dataset()
    print("Wrote dataset to", out)
