import numpy as np
import pandas as pd
import pytest


def _make_synthetic_dataset(n_rows=200):
    symbols = ["BBCA.JK", "ASII.JK"]
    rng = np.random.default_rng(7)
    rows = []

    for symbol in symbols:
        for i in range(n_rows // len(symbols)):
            momentum = rng.normal(0, 1)
            label = -1 if momentum < -0.35 else (1 if momentum > 0.35 else 0)
            rows.append(
                {
                    "symbol": symbol,
                    "t_index": i,
                    "close": 100 + i + rng.normal(0, 1),
                    "volume": 1200 + rng.normal(0, 100),
                    "momentum": momentum,
                    "volatility": abs(rng.normal(0.02, 0.01)),
                    "sentiment_score": rng.normal(0, 1),
                    "cot_open_interest": 1000 + rng.normal(0, 100),
                    "horizon_tag": "short" if i % 2 == 0 else "swing",
                    "label": label,
                }
            )
    return pd.DataFrame(rows)


def test_build_walk_forward_windows_basic():
    from src.ml.walk_forward import build_walk_forward_windows

    windows = build_walk_forward_windows(
        n_samples=120,
        min_train_size=50,
        fold_test_size=20,
        step_size=20,
        purge_gap=2,
        max_folds=3,
    )

    assert len(windows) == 3
    assert windows[0].train_start == 0
    assert windows[0].train_end == 50
    assert windows[0].test_start == 52
    assert windows[0].test_end == 72


def test_evaluate_transformer_walk_forward_smoke(tmp_path):
    pytest.importorskip("torch")
    from src.ml.walk_forward import evaluate_transformer_walk_forward

    df = _make_synthetic_dataset(200)
    dataset_path = tmp_path / "dataset_walk_forward.csv"
    report_path = tmp_path / "walk_forward_report.json"
    model_dir = tmp_path / "walk_forward_models"
    df.to_csv(dataset_path, index=False)

    summary = evaluate_transformer_walk_forward(
        dataset_csv=str(dataset_path),
        architecture="fusion",
        seq_len=10,
        min_train_size=40,
        fold_test_size=16,
        step_size=16,
        purge_gap=1,
        val_size=0.1,
        epochs=1,
        batch_size=16,
        learning_rate=1e-3,
        d_model=32,
        n_heads=4,
        n_layers=1,
        dropout=0.1,
        random_state=42,
        patience=1,
        device="cpu",
        expanding=True,
        max_folds=2,
        model_dir=str(model_dir),
        report_out=str(report_path),
    )

    assert summary["architecture"] == "fusion"
    assert summary["fold_count"] == 2
    assert summary["successful_folds"] >= 1
    assert "aggregate" in summary
    assert report_path.exists()
