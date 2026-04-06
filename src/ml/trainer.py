"""Training utilities for supervised models (LightGBM fallback to sklearn).

Functions:
- `train_model` — train a binary classifier from a dataset CSV and save model.
"""
from __future__ import annotations

import os
from typing import Dict


def train_model(
    dataset_csv: str,
    target_col: str = "label",
    model_out: str = "models/model.joblib",
    test_size: float = 0.2,
    random_state: int = 42,
    use_optuna: bool = True,
    n_trials: int = 20,
    purge_gap: int = 5,
    n_splits: int = 3,
    enable_multimodal: bool = True,
    price_dir: str = "data/prices",
    etl_dir: str = "data",
    horizon_bars: int = 5,
) -> Dict:
    """Train a binary classifier with optional Purged Time-Series CV + Optuna tuning.

    Behaviour:
    - Reads `dataset_csv`, constructs X/y by dropping identifier columns.
    - Performs a chronological holdout for final evaluation (size `test_size`).
    - Optionally runs a PurgedTimeSeriesSplit on the training portion to tune
      LightGBM hyperparameters via Optuna. If Optuna or LightGBM are unavailable
      the function falls back to a sensible default (RandomForest).
        - Optionally augments input dataset with multimodal context (sentiment + COT)
            and horizon tagging using available ETL and price artifacts.
    """
    import pandas as pd
    from sklearn.metrics import classification_report, roc_auc_score

    # attempt a single LightGBM import to avoid repeated redefinitions
    try:
        import lightgbm as lgb  # type: ignore
    except Exception:
        lgb = None

    df = pd.read_csv(dataset_csv)
    if target_col not in df.columns:
        raise RuntimeError(f"{target_col} not in dataset")

    required_multimodal_cols = {
        "horizon_tag",
        "horizon_bars",
        "has_sentiment_features",
        "has_cot_features",
    }
    needs_multimodal_augmentation = not required_multimodal_cols.issubset(df.columns)

    if enable_multimodal and needs_multimodal_augmentation:
        try:
            from src.ml.feature_store import augment_dataset_with_multimodal

            df = augment_dataset_with_multimodal(
                df,
                price_dir=price_dir,
                etl_dir=etl_dir,
                horizon_bars=horizon_bars,
            )
        except Exception:
            # best-effort enrichment only
            pass

    # optional: inject microstructure-derived features (best-effort)
    # This will attempt to add features like 'vwap', 'net_foreign',
    # 'order_book_imbalance' if the source dataframe contains the required
    # columns. Failure is non-fatal.
    try:
        from src.ml.feature_store import (
            calculate_idx_microstructure_features,  # type: ignore
        )

        try:
            df = calculate_idx_microstructure_features(df)
        except Exception:
            # non-fatal: continue without microstructure features
            pass
    except Exception:
        # feature enrichment module not available; skip
        pass

    # drop identifier columns and keep features
    drop_cols = ["symbol", "t_index", "future_return"]
    X = df.drop(columns=[c for c in drop_cols if c in df.columns] + [target_col])
    y = df[target_col]

    # Ensure model matrix is numeric (e.g., horizon_tag from multimodal features).
    for col in X.columns:
        if pd.api.types.is_bool_dtype(X[col]):
            X[col] = X[col].astype(int)
        elif not pd.api.types.is_numeric_dtype(X[col]):
            X[col] = X[col].astype("category").cat.codes.astype(float)

    # prefer forward-fill / backfill for price-like features, then fall back to zero
    # (helps when a few leading rows have NaNs)
    X = X.ffill().bfill().fillna(0.0)

    # Chronological split for final holdout
    split_idx = int(len(X) * (1.0 - float(test_size)))
    if split_idx <= 0 or split_idx >= len(X):
        raise RuntimeError(
            "Invalid split index computed; check dataset size and test_size"
        )

    # Apply a purge gap between train and final holdout to avoid leakage
    holdout_start = split_idx + int(purge_gap)
    if holdout_start >= len(X):
        # fallback: no purge possible (dataset small); use standard chronological split
        X_train = X.iloc[:split_idx].reset_index(drop=True)
        X_test = X.iloc[split_idx:].reset_index(drop=True)
        y_train = y.iloc[:split_idx].reset_index(drop=True)
        y_test = y.iloc[split_idx:].reset_index(drop=True)
    else:
        X_train = X.iloc[:split_idx].reset_index(drop=True)
        X_test = X.iloc[holdout_start:].reset_index(drop=True)
        y_train = y.iloc[:split_idx].reset_index(drop=True)
        y_test = y.iloc[holdout_start:].reset_index(drop=True)

    # Purged Time-Series split helper (expanding training window + purge)
    class PurgedTimeSeriesSplit:
        def __init__(self, n_splits=3, purge_gap=5):
            self.n_splits = int(n_splits)
            self.purge_gap = int(purge_gap)

        def split(self, X_obj):
            n = len(X_obj)
            # allocate validation windows near the end of the training set
            test_size = max(1, n // (self.n_splits + 1))
            start = n - self.n_splits * test_size
            for i in range(self.n_splits):
                val_start = start + i * test_size
                val_end = min(val_start + test_size, n)
                train_end = max(0, val_start - self.purge_gap)
                train_idx = list(range(0, train_end))
                val_idx = list(range(val_start, val_end))
                if len(train_idx) > 0 and len(val_idx) > 0:
                    yield train_idx, val_idx

    best_params = None
    tuned = False

    if use_optuna:
        try:
            import optuna

            if lgb is None:
                # LightGBM required for Optuna tuning in this flow
                raise Exception("lightgbm not available")
            from sklearn.metrics import roc_auc_score as _roc

            def objective(trial):
                params = {
                    "objective": "binary",
                    "metric": "auc",
                    "boosting_type": "gbdt",
                    "num_leaves": trial.suggest_int("num_leaves", 20, 150),
                    "learning_rate": trial.suggest_float(
                        "learning_rate", 1e-3, 0.1, log=True
                    ),
                    "feature_fraction": trial.suggest_float(
                        "feature_fraction", 0.5, 1.0
                    ),
                    "max_depth": trial.suggest_int("max_depth", 3, 12),
                    "n_estimators": 200,
                    "random_state": int(random_state),
                    "n_jobs": -1,
                    "verbose": -1,
                }

                cv = PurgedTimeSeriesSplit(n_splits=n_splits, purge_gap=purge_gap)
                scores = []
                Xn = X_train.reset_index(drop=True)
                yn = y_train.reset_index(drop=True)
                for tr_idx, val_idx in cv.split(Xn):
                    Xtr, Xval = Xn.iloc[tr_idx], Xn.iloc[val_idx]
                    ytr, yval = yn.iloc[tr_idx], yn.iloc[val_idx]
                    clf = lgb.LGBMClassifier(**params)
                    try:
                        clf.fit(
                            Xtr,
                            ytr,
                            eval_set=[(Xval, yval)],
                            early_stopping_rounds=30,
                            verbose=False,
                        )
                    except TypeError:
                        # older LGBM API may not accept verbose/early_stopping kwargs
                        clf.fit(Xtr, ytr)
                    try:
                        probs = clf.predict_proba(Xval)[:, 1]
                        scores.append(float(_roc(yval, probs)))
                    except Exception:
                        preds = clf.predict(Xval)
                        scores.append(float(_roc(yval, preds)))

                return float(sum(scores) / len(scores)) if scores else 0.0

            study = optuna.create_study(direction="maximize")
            study.optimize(objective, n_trials=max(1, int(n_trials)))
            best_params = study.best_params
            tuned = True
        except Exception:
            # optuna or lightgbm not available — continue with defaults
            best_params = None
            tuned = False

    model = None
    # Train final model — prefer LightGBM with best params if available, else fallbacks
    if tuned and best_params is not None and lgb is not None:
        try:
            # ensure deterministic seed preserved
            best_params.setdefault("random_state", int(random_state))
            best_params.setdefault("n_jobs", -1)
            model = lgb.LGBMClassifier(**best_params)
            try:
                model.fit(
                    X_train,
                    y_train,
                    eval_set=[(X_test, y_test)],
                    early_stopping_rounds=50,
                    verbose=False,
                )
            except TypeError:
                # older LGBM API may not accept these args
                model.fit(X_train, y_train)
        except Exception:
            model = None

    if model is None:
        try:
            # try to lazily import LightGBM if not already available
            if lgb is None:
                import importlib

                lgb = importlib.import_module("lightgbm")

            model = lgb.LGBMClassifier(n_jobs=-1, random_state=random_state)
            model.fit(X_train, y_train)
        except Exception:
            from sklearn.ensemble import RandomForestClassifier

            model = RandomForestClassifier(
                n_estimators=100, n_jobs=-1, random_state=random_state
            )
            model.fit(X_train, y_train)

    preds = model.predict(X_test)
    probs = None
    try:
        probs = model.predict_proba(X_test)[:, 1]
    except Exception:
        pass

    report = classification_report(y_test, preds, output_dict=True)
    auc = roc_auc_score(y_test, probs) if probs is not None else None

    # persist model and metadata
    os.makedirs(os.path.dirname(model_out) or ".", exist_ok=True)
    try:
        import joblib

        joblib.dump(
            {"model": model, "features": list(X.columns), "tuned": tuned},
            model_out,
        )
    except Exception:
        import pickle

        with open(model_out, "wb") as fh:
            pickle.dump(
                {"model": model, "features": list(X.columns), "tuned": tuned},
                fh,
            )

    # SECURITY FIX V: Export to ONNX format (safe serialization, no RCE vector)
    try:
        from skl2onnx import convert_sklearn
        from skl2onnx.common.data_types import FloatTensorType

        onnx_path = model_out.replace(".joblib", ".onnx").replace(".pkl", ".onnx")
        initial_type = [("float_input", FloatTensorType([None, len(X.columns)]))]
        onnx_model = convert_sklearn(model, initial_types=initial_type)

        with open(onnx_path, "wb") as f:
            f.write(onnx_model.SerializeToString())
    except Exception:
        pass  # ONNX export is optional; continue if unavailable

    return {
        "model_path": model_out,
        "report": report,
        "roc_auc": auc,
        "tuned": tuned,
    }


if __name__ == "__main__":
    print(
        "This module provides `train_model()`; "
        "run scripts/train_model.py to train a model."
    )
