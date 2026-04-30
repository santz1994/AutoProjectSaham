import os

import numpy as np
import pandas as pd
import pytest


def _make_synthetic_dataset(n_rows=120):
    symbols = ["BTC-USD", "EURUSD=X"]
    rows = []
    rng = np.random.default_rng(42)
    for symbol in symbols:
        for i in range(n_rows // len(symbols)):
            close = 100 + i + rng.normal(0, 1)
            momentum = rng.normal(0, 1)
            label = -1 if momentum < -0.4 else (1 if momentum > 0.4 else 0)
            rows.append(
                {
                    "symbol": symbol,
                    "t_index": i,
                    "close": close,
                    "volume": 1000 + rng.normal(0, 50),
                    "momentum": momentum,
                    "horizon_tag": "short" if i % 2 == 0 else "swing",
                    "label": label,
                }
            )
    return pd.DataFrame(rows)


def test_prepare_sequence_data_shapes():
    from src.ml.transformer_baselines import prepare_sequence_data

    df = _make_synthetic_dataset(120)
    split = prepare_sequence_data(df, seq_len=12, test_size=0.2, purge_gap=2)

    assert split.x_train.ndim == 3
    assert split.x_val.ndim == 3
    assert split.x_test.ndim == 3
    assert split.x_train.shape[1] == 12
    assert split.x_train.shape[2] > 0
    assert split.y_train.ndim == 1
    assert len(split.label_to_index) >= 2


def test_infer_feature_partitions_detects_multimodal_columns():
    from src.ml.transformer_baselines import infer_feature_partitions

    feature_columns = [
        "last_price",
        "short_sma",
        "long_sma",
        "volatility",
        "sentiment_score",
        "cot_open_interest",
        "horizon_tag",
    ]
    parts = infer_feature_partitions(feature_columns)

    assert len(parts["technical_indices"]) > 0
    assert len(parts["context_indices"]) > 0
    assert 4 in parts["context_indices"]
    assert 5 in parts["context_indices"]
    assert 6 in parts["context_indices"]


@pytest.mark.parametrize("architecture", ["patchtst", "mtst", "tft", "fusion"])
def test_build_baseline_model_forward(architecture):
    torch = pytest.importorskip("torch")
    from src.ml.transformer_baselines import build_baseline_model

    extra_kwargs = {}
    if architecture == "fusion":
        extra_kwargs["feature_columns"] = [
            "last_price",
            "short_sma",
            "long_sma",
            "volatility",
            "sentiment_score",
            "cot_open_interest",
            "horizon_tag",
            "has_sentiment_features",
        ]

    model = build_baseline_model(
        architecture=architecture,
        input_dim=8,
        num_classes=3,
        patch_sizes=[4, 8],
        d_model=64,
        n_heads=4,
        n_layers=1,
        dropout=0.1,
        **extra_kwargs,
    ).to(torch.device("cpu"))

    x = torch.randn(5, 16, 8)
    logits = model(x)
    assert logits.shape == (5, 3)


def test_train_transformer_baseline_smoke(tmp_path):
    pytest.importorskip("torch")
    from src.ml.transformer_baselines import train_transformer_baseline

    df = _make_synthetic_dataset(120)
    dataset_path = tmp_path / "dataset.csv"
    model_path = tmp_path / "patchtst_baseline.pt"
    df.to_csv(dataset_path, index=False)

    result = train_transformer_baseline(
        dataset_csv=str(dataset_path),
        architecture="patchtst",
        model_out=str(model_path),
        seq_len=10,
        epochs=1,
        batch_size=16,
        d_model=64,
        n_heads=4,
        n_layers=1,
        patch_sizes=[5],
        random_state=42,
        patience=1,
        test_size=0.2,
        purge_gap=1,
        device="cpu",
    )

    assert os.path.exists(model_path)
    assert result["architecture"] == "patchtst"
    assert "metrics" in result
    assert "accuracy" in result["metrics"]


def test_train_transformer_fusion_smoke(tmp_path):
    pytest.importorskip("torch")
    from src.ml.transformer_baselines import train_transformer_baseline

    df = _make_synthetic_dataset(120)
    df["sentiment_score"] = np.sin(np.linspace(0, 3.14, len(df)))
    df["cot_open_interest"] = np.linspace(1000, 1200, len(df))
    df["has_sentiment_features"] = 1

    dataset_path = tmp_path / "dataset_fusion.csv"
    model_path = tmp_path / "fusion_baseline.pt"
    df.to_csv(dataset_path, index=False)

    result = train_transformer_baseline(
        dataset_csv=str(dataset_path),
        architecture="fusion",
        model_out=str(model_path),
        seq_len=10,
        epochs=1,
        batch_size=16,
        d_model=64,
        n_heads=4,
        n_layers=1,
        random_state=42,
        patience=1,
        test_size=0.2,
        purge_gap=1,
        device="cpu",
    )

    assert os.path.exists(model_path)
    assert result["architecture"] == "fusion"
    assert "metrics" in result
    assert "accuracy" in result["metrics"]
