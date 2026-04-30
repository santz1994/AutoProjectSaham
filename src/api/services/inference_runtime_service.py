"""Helpers for transformer runtime loading and sequence preparation."""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional


def resolve_signal_universe(
    df: Any,
    preferred_universe: Optional[List[str]],
    max_symbols: int,
    *,
    symbols_match_fn: Callable[[str, str], bool],
) -> List[str]:
    if "symbol" not in df.columns:
        return []

    available_symbols = [str(value) for value in df["symbol"].dropna().astype(str).tolist()]
    selected: List[str] = []

    for symbol in preferred_universe or []:
        normalized = str(symbol).strip()
        if not normalized:
            continue

        exact_match = next(
            (item for item in available_symbols if item == normalized),
            None,
        )
        if exact_match and exact_match not in selected:
            selected.append(exact_match)
            continue

        alias_match = next(
            (item for item in available_symbols if symbols_match_fn(item, normalized)),
            None,
        )
        if alias_match and alias_match not in selected:
            selected.append(alias_match)

    if not selected:
        if "t_index" in df.columns:
            latest = (
                df[["symbol", "t_index"]]
                .dropna(subset=["symbol"])
                .groupby("symbol", as_index=False)["t_index"]
                .max()
                .sort_values("t_index", ascending=False)
            )
            for value in latest["symbol"].tolist():
                symbol = str(value)
                if symbol not in selected:
                    selected.append(symbol)
        else:
            for symbol in available_symbols:
                if symbol not in selected:
                    selected.append(symbol)

    safe_max = max(1, int(max_symbols))
    return selected[:safe_max]


def load_transformer_runtime(
    *,
    project_root: Optional[str],
    get_project_root_fn: Callable[[], str],
    resolve_best_transformer_artifact_fn: Callable[[Optional[str]], Optional[Dict[str, Any]]],
    transformer_runtime_cache: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    root = project_root or get_project_root_fn()
    best_artifact = resolve_best_transformer_artifact_fn(root)
    if not best_artifact:
        return None

    model_path = best_artifact.get("path")
    model_mtime = best_artifact.get("mtime")
    if (
        transformer_runtime_cache.get("runtime") is not None
        and transformer_runtime_cache.get("path") == model_path
        and transformer_runtime_cache.get("mtime") == model_mtime
    ):
        return transformer_runtime_cache.get("runtime")

    try:
        import numpy as np
        import torch
        from src.ml.transformer_baselines import build_baseline_model

        checkpoint = torch.load(model_path, map_location="cpu")
        if not isinstance(checkpoint, dict):
            return None

        feature_columns = [str(col) for col in (checkpoint.get("feature_columns") or [])]
        if not feature_columns:
            return None

        architecture = str(
            checkpoint.get("architecture")
            or best_artifact.get("architecture")
            or "fusion"
        ).lower()
        train_config = checkpoint.get("train_config") or {}

        input_dim = int(checkpoint.get("input_dim") or len(feature_columns))
        raw_index_to_label = checkpoint.get("index_to_label") or {}
        num_classes = int(checkpoint.get("num_classes") or max(2, len(raw_index_to_label)))

        model = build_baseline_model(
            architecture=architecture,
            input_dim=input_dim,
            num_classes=num_classes,
            feature_columns=feature_columns,
            patch_sizes=train_config.get("patch_sizes") or [4, 8, 16],
            patch_stride=int(train_config.get("patch_stride", 4)),
            d_model=int(train_config.get("d_model", 128)),
            n_heads=int(train_config.get("n_heads", 4)),
            n_layers=int(train_config.get("n_layers", 2)),
            dropout=float(train_config.get("dropout", 0.1)),
        )

        state_dict = checkpoint.get("state_dict")
        if not state_dict:
            return None
        model.load_state_dict(state_dict)
        model.eval()

        mean_values = checkpoint.get("normalization_mean") or [0.0] * input_dim
        std_values = checkpoint.get("normalization_std") or [1.0] * input_dim
        mean = np.asarray(mean_values, dtype=np.float32).reshape(1, 1, -1)
        std = np.asarray(std_values, dtype=np.float32).reshape(1, 1, -1)
        std = np.where(abs(std) < 1e-6, 1.0, std).astype(np.float32)

        index_to_label: Dict[int, int] = {}
        for key, value in raw_index_to_label.items():
            try:
                idx = int(key)
                index_to_label[idx] = int(value)
            except Exception:
                continue

        runtime = {
            "model": model,
            "feature_columns": feature_columns,
            "normalization_mean": mean,
            "normalization_std": std,
            "index_to_label": index_to_label,
            "architecture": architecture,
            "source": best_artifact.get("source") or "transformer",
            "seq_len": int(train_config.get("seq_len", 32)),
        }

        transformer_runtime_cache.update(
            {
                "path": model_path,
                "mtime": model_mtime,
                "runtime": runtime,
            }
        )
        return runtime
    except Exception:
        transformer_runtime_cache.update(
            {"path": model_path, "mtime": model_mtime, "runtime": None}
        )
        return None


def estimate_label_returns(df: Any) -> Dict[int, float]:
    if "label" not in df.columns or "future_return" not in df.columns:
        return {}

    stats: Dict[int, float] = {}
    grouped = (
        df[["label", "future_return"]]
        .dropna(subset=["label", "future_return"])
        .groupby("label")["future_return"]
        .mean()
    )
    for label, value in grouped.items():
        try:
            stats[int(label)] = float(value)
        except Exception:
            continue
    return stats


def build_symbol_sequences(
    df: Any,
    feature_columns: List[str],
    seq_len: int,
    symbols: List[str],
    *,
    safe_float_fn: Callable[[Any, Optional[float]], Optional[float]],
) -> List[Dict[str, Any]]:
    import numpy as np
    import pandas as pd

    if "symbol" not in df.columns or not feature_columns:
        return []

    work = df.copy()
    if "t_index" not in work.columns:
        work["t_index"] = np.arange(len(work), dtype=int)

    work["_row_order"] = np.arange(len(work), dtype=int)
    work = work.sort_values(["symbol", "t_index", "_row_order"], kind="mergesort").reset_index(drop=True)

    for col in feature_columns:
        if col not in work.columns:
            work[col] = 0.0

    for col in feature_columns:
        if pd.api.types.is_bool_dtype(work[col]):
            work[col] = work[col].astype(int)
        elif not pd.api.types.is_numeric_dtype(work[col]):
            work[col] = work[col].astype("category").cat.codes.astype(float)

    feature_frame = (
        work[feature_columns]
        .replace([np.inf, -np.inf], np.nan)
        .ffill()
        .bfill()
        .fillna(0.0)
        .astype(np.float32)
    )

    price_col = None
    for candidate in ["last_price", "close", "price", "adj_close", "open"]:
        if candidate in work.columns:
            price_col = candidate
            break

    samples: List[Dict[str, Any]] = []
    for symbol in symbols:
        symbol_mask = work["symbol"].astype(str) == str(symbol)
        if not bool(symbol_mask.any()):
            continue

        symbol_features = feature_frame.loc[symbol_mask].to_numpy(dtype=np.float32)
        if symbol_features.shape[0] < 1:
            continue

        if symbol_features.shape[0] >= seq_len:
            sequence = symbol_features[-seq_len:]
        else:
            pad = np.repeat(symbol_features[:1], repeats=(seq_len - symbol_features.shape[0]), axis=0)
            sequence = np.concatenate([pad, symbol_features], axis=0)

        symbol_rows = work.loc[symbol_mask]
        last_row = symbol_rows.iloc[-1]
        current_price = safe_float_fn(last_row.get(price_col), default=0.0) if price_col else 0.0

        samples.append(
            {
                "symbol": str(symbol),
                "sequence": sequence,
                "current_price": float(max(0.0, current_price or 0.0)),
            }
        )

    return samples
