from __future__ import annotations

import asyncio
import os

import pandas as pd
import pytest

from src.api import frontend_routes
from src.ml.transformer_baselines import build_baseline_model


def _make_dataset_csv(path: str) -> None:
    rows = []
    for symbol, base_price in [("AAA.JK", 100.0), ("BBB.JK", 75.0)]:
        for t_index in range(16):
            future_return = 0.02 if (t_index % 4 == 0) else -0.01
            rows.append(
                {
                    "symbol": symbol,
                    "t_index": t_index,
                    "future_return": future_return,
                    "label": 1 if future_return > 0 else 0,
                    "last_price": base_price + (t_index * 0.5),
                    "short_sma": base_price + (t_index * 0.45),
                    "long_sma": base_price + (t_index * 0.40),
                    "momentum": (t_index - 8) / 100.0,
                }
            )
    pd.DataFrame(rows).to_csv(path, index=False)


def _make_transformer_checkpoint(path: str) -> None:
    torch = pytest.importorskip("torch")

    feature_columns = ["last_price", "short_sma", "long_sma", "momentum"]
    model = build_baseline_model(
        architecture="fusion",
        input_dim=len(feature_columns),
        num_classes=2,
        feature_columns=feature_columns,
        patch_sizes=[4, 8],
        patch_stride=2,
        d_model=16,
        n_heads=4,
        n_layers=1,
        dropout=0.1,
    )

    checkpoint = {
        "architecture": "fusion",
        "input_dim": len(feature_columns),
        "num_classes": 2,
        "feature_columns": feature_columns,
        "label_to_index": {0: 0, 1: 1},
        "index_to_label": {0: 0, 1: 1},
        "state_dict": model.state_dict(),
        "normalization_mean": [0.0, 0.0, 0.0, 0.0],
        "normalization_std": [1.0, 1.0, 1.0, 1.0],
        "train_config": {
            "seq_len": 8,
            "patch_sizes": [4, 8],
            "patch_stride": 2,
            "d_model": 16,
            "n_heads": 4,
            "n_layers": 1,
            "dropout": 0.1,
        },
    }
    torch.save(checkpoint, path)


def test_infer_signals_from_transformer_with_temp_artifact(tmp_path, monkeypatch):
    dataset_csv = tmp_path / "dataset.csv"
    model_path = tmp_path / "fusion_unit_test.pt"

    _make_dataset_csv(str(dataset_csv))
    _make_transformer_checkpoint(str(model_path))

    artifact = {
        "path": str(model_path),
        "artifact": str(model_path),
        "mtime": os.path.getmtime(model_path),
        "lastTrainedAt": "2026-01-01T00:00:00",
        "architecture": "fusion",
        "source": "unit_test",
        "score": 0.5,
    }

    monkeypatch.setattr(frontend_routes, "_resolve_dataset_csv_path", lambda: str(dataset_csv))
    monkeypatch.setattr(
        frontend_routes,
        "_resolve_best_transformer_artifact",
        lambda project_root=None: artifact,
    )
    frontend_routes._transformer_runtime_cache.update({"path": None, "mtime": None, "runtime": None})

    signals = frontend_routes._infer_signals_from_transformer(
        limit=3,
        preferred_universe=["AAA.JK"],
    )

    assert signals
    assert len(signals) == 1
    assert signals[0].symbol == "AAA.JK"
    assert signals[0].signal in {"STRONG_BUY", "BUY", "HOLD", "SELL", "STRONG_SELL"}
    assert 0.0 <= signals[0].confidence <= 1.0


def test_get_signals_prefers_transformer_path(monkeypatch):
    transformer_output = [
        frontend_routes.Signal(
            id=1,
            symbol="AAA.JK",
            name="AAA",
            signal="BUY",
            confidence=0.7,
            reason="model",
            predictedMove="+1.00%",
            riskLevel="Low-Medium",
            sector="IDX",
            currentPrice=100.0,
            targetPrice=101.0,
            timestamp="2026-01-01T00:00:00",
        )
    ]

    fallback_called = {"value": False}

    monkeypatch.setattr(
        frontend_routes,
        "_infer_signals_from_transformer",
        lambda limit, preferred_universe: transformer_output,
    )

    def _fallback(limit, preferred_universe):
        fallback_called["value"] = True
        return []

    monkeypatch.setattr(frontend_routes, "_build_fallback_signals", _fallback)
    monkeypatch.setattr(
        frontend_routes._state_store,
        "get_user_settings",
        lambda defaults: {"preferredUniverse": ["AAA.JK"]},
    )

    output = asyncio.run(frontend_routes.get_signals(limit=1))
    assert len(output) == 1
    assert output[0].symbol == "AAA.JK"
    assert fallback_called["value"] is False


def test_get_signals_fallback_when_transformer_empty(monkeypatch):
    fallback_output = [
        frontend_routes.Signal(
            id=1,
            symbol="FALL.JK",
            name="Fallback",
            signal="HOLD",
            confidence=0.5,
            reason="fallback",
            predictedMove="+0.00%",
            riskLevel="Medium",
            sector="IDX",
            currentPrice=50.0,
            targetPrice=50.0,
            timestamp="2026-01-01T00:00:00",
        )
    ]

    monkeypatch.setattr(
        frontend_routes,
        "_infer_signals_from_transformer",
        lambda limit, preferred_universe: [],
    )
    monkeypatch.setattr(
        frontend_routes,
        "_build_fallback_signals",
        lambda limit, preferred_universe: fallback_output,
    )
    monkeypatch.setattr(
        frontend_routes._state_store,
        "get_user_settings",
        lambda defaults: {"preferredUniverse": ["FALL.JK"]},
    )

    output = asyncio.run(frontend_routes.get_signals(limit=1))
    assert len(output) == 1
    assert output[0].symbol == "FALL.JK"


def test_latest_model_artifact_prefers_transformer(monkeypatch):
    monkeypatch.setattr(
        frontend_routes,
        "_resolve_best_transformer_artifact",
        lambda project_root=None: {
            "artifact": "models/transformers/fusion_baseline.pt",
            "lastTrainedAt": "2026-01-01T00:00:00",
            "architecture": "fusion",
            "source": "baseline",
            "score": 0.33,
        },
    )

    artifact = frontend_routes._get_latest_model_artifact()
    assert artifact["artifact"] == "models/transformers/fusion_baseline.pt"
    assert artifact["architecture"] == "fusion"
