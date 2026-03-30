"""Training utilities for supervised models (LightGBM fallback to sklearn).

Functions:
- `train_model` — train a binary classifier from a dataset CSV and save model.
"""
from __future__ import annotations

import os
from typing import Dict


def train_model(dataset_csv: str, target_col: str = 'label', model_out: str = 'models/model.joblib', test_size: float = 0.2, random_state: int = 42) -> Dict:
    import pandas as pd
    from sklearn.metrics import classification_report, roc_auc_score

    df = pd.read_csv(dataset_csv)
    if target_col not in df.columns:
        raise RuntimeError(f'{target_col} not in dataset')

    # simple feature columns: drop identifier columns
    drop_cols = ['symbol', 't_index', 'future_return']
    X = df.drop(columns=[c for c in drop_cols if c in df.columns] + [target_col])
    y = df[target_col]

    # fill na
    X = X.fillna(0.0)

    # Chronological split for time-series data to avoid data leakage.
    split_idx = int(len(X) * (1.0 - float(test_size)))
    if split_idx <= 0 or split_idx >= len(X):
        raise RuntimeError('Invalid split index computed; check dataset size and test_size')

    X_train = X.iloc[:split_idx].reset_index(drop=True)
    X_test = X.iloc[split_idx:].reset_index(drop=True)
    y_train = y.iloc[:split_idx].reset_index(drop=True)
    y_test = y.iloc[split_idx:].reset_index(drop=True)

    model = None
    try:
        import lightgbm as lgb
        model = lgb.LGBMClassifier(n_jobs=-1, random_state=random_state)
        model.fit(X_train, y_train)
    except Exception:
        # fallback to sklearn
        from sklearn.ensemble import RandomForestClassifier
        model = RandomForestClassifier(n_estimators=100, n_jobs=-1, random_state=random_state)
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
    os.makedirs(os.path.dirname(model_out) or '.', exist_ok=True)
    try:
        import joblib
        joblib.dump({'model': model, 'features': list(X.columns)}, model_out)
    except Exception:
        # fallback: pickle
        import pickle
        with open(model_out, 'wb') as fh:
            pickle.dump({'model': model, 'features': list(X.columns)}, fh)

    return {'model_path': model_out, 'report': report, 'roc_auc': auc}


if __name__ == '__main__':
    print('This module provides `train_model()`; run scripts/train_model.py to train a model.')
