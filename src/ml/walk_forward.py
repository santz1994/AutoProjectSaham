"""Walk-forward evaluation for transformer-based financial classifiers.

This module provides a lightweight, reproducible walk-forward pipeline that
uses chronological train/test folds with an optional purge gap and expanding
or rolling training windows.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, List, Optional, Sequence

import numpy as np
import pandas as pd

from src.ml.transformer_baselines import (
    ID_COLUMNS,
    TimeSeriesTensorDataset,
    _classification_metrics,
    _evaluate,
    _train_one_epoch,
    build_baseline_model,
    set_global_seed,
)


@dataclass
class SequenceDataset:
    """Chronologically ordered sequence dataset used by walk-forward folds."""

    x_all: np.ndarray
    y_all: np.ndarray
    feature_columns: List[str]
    label_to_index: Dict[int, int]
    index_to_label: Dict[int, int]


@dataclass
class WalkForwardWindow:
    """A single walk-forward fold window."""

    train_start: int
    train_end: int
    test_start: int
    test_end: int


def _prepare_feature_frame(df: pd.DataFrame, target_col: str) -> pd.DataFrame:
    drop_cols = set(ID_COLUMNS)
    drop_cols.add(target_col)
    feature_df = df.drop(columns=[c for c in drop_cols if c in df.columns], errors="ignore").copy()

    for col in feature_df.columns:
        if pd.api.types.is_bool_dtype(feature_df[col]):
            feature_df[col] = feature_df[col].astype(int)
        elif not pd.api.types.is_numeric_dtype(feature_df[col]):
            feature_df[col] = feature_df[col].astype("category").cat.codes.astype(float)

    return (
        feature_df
        .replace([np.inf, -np.inf], np.nan)
        .ffill()
        .bfill()
        .fillna(0.0)
        .astype(np.float32)
    )


def build_sequence_dataset(
    df: pd.DataFrame,
    target_col: str = "label",
    group_col: str = "symbol",
    time_col: str = "t_index",
    seq_len: int = 32,
) -> SequenceDataset:
    """Convert raw labeled rows into ordered sequence tensors."""

    if target_col not in df.columns:
        raise RuntimeError(f"{target_col} not found in dataset")
    if seq_len < 2:
        raise RuntimeError("seq_len must be >= 2")

    work = df.copy()
    if group_col not in work.columns:
        work[group_col] = "__single__"
    if time_col not in work.columns:
        work[time_col] = np.arange(len(work), dtype=int)

    work["_global_position"] = np.arange(len(work), dtype=int)
    work = work.sort_values([group_col, time_col, "_global_position"], kind="mergesort").reset_index(drop=True)

    feature_df = _prepare_feature_frame(work, target_col=target_col)
    raw_labels = work[target_col].to_numpy()
    unique_labels = sorted(int(v) for v in np.unique(raw_labels))

    if len(unique_labels) < 2:
        raise RuntimeError("Need at least 2 classes for walk-forward evaluation")

    label_to_index = {label: idx for idx, label in enumerate(unique_labels)}
    index_to_label = {idx: label for label, idx in label_to_index.items()}
    encoded_labels = np.array([label_to_index[int(v)] for v in raw_labels], dtype=np.int64)

    sequences: List[np.ndarray] = []
    targets: List[int] = []
    positions: List[int] = []

    for _, g in work.groupby(group_col, sort=False):
        g_idx = g.index.to_numpy()
        if len(g_idx) < seq_len:
            continue

        g_features = feature_df.iloc[g_idx].to_numpy(dtype=np.float32)
        g_labels = encoded_labels[g_idx]
        g_positions = g["_global_position"].to_numpy(dtype=np.int64)

        for end in range(seq_len - 1, len(g_idx)):
            start = end - seq_len + 1
            sequences.append(g_features[start : end + 1])
            targets.append(int(g_labels[end]))
            positions.append(int(g_positions[end]))

    if not sequences:
        raise RuntimeError("No sequence samples generated for walk-forward")

    x_all = np.stack(sequences).astype(np.float32)
    y_all = np.array(targets, dtype=np.int64)
    pos_all = np.array(positions, dtype=np.int64)

    order = np.argsort(pos_all)
    x_all = x_all[order]
    y_all = y_all[order]

    return SequenceDataset(
        x_all=x_all,
        y_all=y_all,
        feature_columns=list(feature_df.columns),
        label_to_index=label_to_index,
        index_to_label=index_to_label,
    )


def build_walk_forward_windows(
    n_samples: int,
    min_train_size: int,
    fold_test_size: int,
    step_size: Optional[int] = None,
    purge_gap: int = 0,
    expanding: bool = True,
    max_folds: Optional[int] = None,
) -> List[WalkForwardWindow]:
    """Build chronological walk-forward windows."""

    if n_samples <= 0:
        raise RuntimeError("n_samples must be > 0")
    if min_train_size < 2:
        raise RuntimeError("min_train_size must be >= 2")
    if fold_test_size < 1:
        raise RuntimeError("fold_test_size must be >= 1")
    if purge_gap < 0:
        raise RuntimeError("purge_gap must be >= 0")

    step = int(step_size or fold_test_size)
    if step < 1:
        raise RuntimeError("step_size must be >= 1")

    windows: List[WalkForwardWindow] = []
    train_end = int(min_train_size)

    while True:
        test_start = train_end + int(purge_gap)
        test_end = test_start + int(fold_test_size)
        if test_end > n_samples:
            break

        train_start = 0 if expanding else max(0, train_end - int(min_train_size))
        windows.append(
            WalkForwardWindow(
                train_start=int(train_start),
                train_end=int(train_end),
                test_start=int(test_start),
                test_end=int(test_end),
            )
        )

        if max_folds is not None and len(windows) >= int(max_folds):
            break
        train_end += step

    if not windows:
        raise RuntimeError(
            "No walk-forward windows generated; reduce min_train_size/fold_test_size or increase data"
        )
    return windows


def _normalize_by_train(
    x_train: np.ndarray,
    x_val: np.ndarray,
    x_test: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    mean = x_train.mean(axis=(0, 1), keepdims=True)
    std = x_train.std(axis=(0, 1), keepdims=True)
    std = np.where(std < 1e-6, 1.0, std)

    return (
        ((x_train - mean) / std).astype(np.float32),
        ((x_val - mean) / std).astype(np.float32),
        ((x_test - mean) / std).astype(np.float32),
        mean.astype(np.float32),
        std.astype(np.float32),
    )


def evaluate_transformer_walk_forward(
    dataset_csv: str,
    architecture: str = "fusion",
    target_col: str = "label",
    seq_len: int = 32,
    min_train_size: int = 300,
    fold_test_size: int = 100,
    step_size: Optional[int] = None,
    purge_gap: int = 5,
    val_size: float = 0.1,
    epochs: int = 5,
    batch_size: int = 64,
    learning_rate: float = 1e-3,
    patch_sizes: Optional[Sequence[int]] = None,
    patch_stride: int = 4,
    d_model: int = 128,
    n_heads: int = 4,
    n_layers: int = 2,
    dropout: float = 0.1,
    random_state: int = 42,
    device: Optional[str] = None,
    patience: int = 3,
    expanding: bool = True,
    max_folds: Optional[int] = None,
    model_dir: Optional[str] = None,
    report_out: Optional[str] = None,
) -> Dict:
    """Run walk-forward transformer evaluation and return fold summaries."""

    import torch

    if not os.path.exists(dataset_csv):
        raise RuntimeError(f"Dataset not found: {dataset_csv}")

    set_global_seed(random_state)
    df = pd.read_csv(dataset_csv)
    sequence_data = build_sequence_dataset(
        df,
        target_col=target_col,
        seq_len=seq_len,
    )

    windows = build_walk_forward_windows(
        n_samples=len(sequence_data.x_all),
        min_train_size=min_train_size,
        fold_test_size=fold_test_size,
        step_size=step_size,
        purge_gap=purge_gap,
        expanding=expanding,
        max_folds=max_folds,
    )

    resolved_device = device or ("cuda" if torch.cuda.is_available() else "cpu")
    device_obj = torch.device(resolved_device)
    num_classes = int(len(sequence_data.label_to_index))

    if model_dir:
        os.makedirs(model_dir, exist_ok=True)

    fold_results: List[Dict] = []
    for fold_number, window in enumerate(windows, start=1):
        x_train_all = sequence_data.x_all[window.train_start : window.train_end]
        y_train_all = sequence_data.y_all[window.train_start : window.train_end]
        x_test = sequence_data.x_all[window.test_start : window.test_end]
        y_test = sequence_data.y_all[window.test_start : window.test_end]

        if len(x_train_all) < 2 or len(x_test) < 1:
            fold_results.append(
                {
                    "fold": fold_number,
                    "window": window.__dict__,
                    "status": "skipped",
                    "reason": "insufficient_samples",
                }
            )
            continue

        val_count = int(len(x_train_all) * float(val_size))
        if val_count < 1 and len(x_train_all) >= 20:
            val_count = 1

        if val_count > 0 and (len(x_train_all) - val_count) >= 1:
            x_train = x_train_all[:-val_count]
            y_train = y_train_all[:-val_count]
            x_val = x_train_all[-val_count:]
            y_val = y_train_all[-val_count:]
        else:
            x_train = x_train_all
            y_train = y_train_all
            x_val = x_test
            y_val = y_test

        x_train, x_val, x_test, mean, std = _normalize_by_train(x_train, x_val, x_test)

        model = build_baseline_model(
            architecture=architecture,
            input_dim=int(x_train.shape[-1]),
            num_classes=num_classes,
            feature_columns=sequence_data.feature_columns,
            patch_sizes=patch_sizes,
            patch_stride=patch_stride,
            d_model=d_model,
            n_heads=n_heads,
            n_layers=n_layers,
            dropout=dropout,
        ).to(device_obj)

        train_dataset = TimeSeriesTensorDataset(x_train, y_train)
        val_dataset = TimeSeriesTensorDataset(x_val, y_val)
        test_dataset = TimeSeriesTensorDataset(x_test, y_test)

        train_loader = torch.utils.data.DataLoader(train_dataset, batch_size=batch_size, shuffle=True)
        val_loader = torch.utils.data.DataLoader(val_dataset, batch_size=batch_size, shuffle=False)
        test_loader = torch.utils.data.DataLoader(test_dataset, batch_size=batch_size, shuffle=False)

        class_counts = np.bincount(y_train, minlength=num_classes)
        class_weights = len(y_train) / np.maximum(class_counts, 1)
        class_weights = class_weights / class_weights.sum() * num_classes

        criterion = torch.nn.CrossEntropyLoss(
            weight=torch.tensor(class_weights, dtype=torch.float32, device=device_obj)
        )
        optimizer = torch.optim.AdamW(model.parameters(), lr=learning_rate, weight_decay=1e-4)

        best_state = None
        best_val_loss = float("inf")
        no_improve = 0
        history: List[Dict] = []

        for epoch in range(1, max(1, int(epochs)) + 1):
            train_loss = _train_one_epoch(model, train_loader, optimizer, criterion, device_obj)
            val_loss, _, _ = _evaluate(model, val_loader, criterion, device_obj)

            history.append(
                {
                    "epoch": int(epoch),
                    "train_loss": float(train_loss),
                    "val_loss": float(val_loss),
                }
            )

            if val_loss < best_val_loss:
                best_val_loss = val_loss
                best_state = model.state_dict()
                no_improve = 0
            else:
                no_improve += 1
                if no_improve >= max(1, int(patience)):
                    break

        if best_state is not None:
            model.load_state_dict(best_state)

        test_loss, test_logits, test_labels = _evaluate(model, test_loader, criterion, device_obj)
        metrics = _classification_metrics(test_labels, test_logits)
        metrics["test_loss"] = float(test_loss)
        metrics["best_val_loss"] = float(best_val_loss)

        fold_model_path = None
        if model_dir:
            fold_model_path = os.path.join(model_dir, f"{architecture.lower()}_fold_{fold_number}.pt")
            checkpoint = {
                "architecture": architecture.lower(),
                "fold": int(fold_number),
                "window": window.__dict__,
                "feature_columns": sequence_data.feature_columns,
                "label_to_index": sequence_data.label_to_index,
                "index_to_label": sequence_data.index_to_label,
                "normalization_mean": mean.squeeze(0).squeeze(0).tolist(),
                "normalization_std": std.squeeze(0).squeeze(0).tolist(),
                "state_dict": model.state_dict(),
                "metrics": metrics,
                "history": history,
            }
            torch.save(checkpoint, fold_model_path)

        fold_results.append(
            {
                "fold": int(fold_number),
                "window": window.__dict__,
                "status": "ok",
                "num_samples": {
                    "train": int(len(x_train)),
                    "val": int(len(x_val)),
                    "test": int(len(x_test)),
                },
                "metrics": metrics,
                "history": history,
                "model_path": fold_model_path,
            }
        )

    valid_folds = [f for f in fold_results if f.get("status") == "ok"]
    aggregate: Dict[str, Optional[float]] = {}
    for metric_name in ["accuracy", "f1_macro", "f1_weighted", "roc_auc_ovr_weighted", "test_loss"]:
        values = [f["metrics"].get(metric_name) for f in valid_folds]
        clean = [float(v) for v in values if v is not None]
        aggregate[f"{metric_name}_mean"] = float(np.mean(clean)) if clean else None
        aggregate[f"{metric_name}_std"] = float(np.std(clean)) if clean else None

    summary = {
        "dataset_csv": dataset_csv,
        "architecture": architecture.lower(),
        "generated_at": datetime.now(tz=timezone.utc).isoformat(),
        "config": {
            "seq_len": int(seq_len),
            "min_train_size": int(min_train_size),
            "fold_test_size": int(fold_test_size),
            "step_size": int(step_size or fold_test_size),
            "purge_gap": int(purge_gap),
            "val_size": float(val_size),
            "epochs": int(epochs),
            "batch_size": int(batch_size),
            "learning_rate": float(learning_rate),
            "d_model": int(d_model),
            "n_heads": int(n_heads),
            "n_layers": int(n_layers),
            "dropout": float(dropout),
            "random_state": int(random_state),
            "device": resolved_device,
            "expanding": bool(expanding),
            "max_folds": int(max_folds) if max_folds is not None else None,
        },
        "fold_count": int(len(windows)),
        "successful_folds": int(len(valid_folds)),
        "aggregate": aggregate,
        "results": fold_results,
    }

    if report_out:
        os.makedirs(os.path.dirname(report_out) or ".", exist_ok=True)
        with open(report_out, "w", encoding="utf-8") as handle:
            json.dump(summary, handle, indent=2)

    return summary


__all__ = [
    "build_sequence_dataset",
    "build_walk_forward_windows",
    "evaluate_transformer_walk_forward",
    "SequenceDataset",
    "WalkForwardWindow",
]
