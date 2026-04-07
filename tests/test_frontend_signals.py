from __future__ import annotations

import asyncio
import os

import numpy as np
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


def test_get_ai_projection_uses_anchor_and_timeframe(monkeypatch):
    monkeypatch.setattr(
        frontend_routes,
        "_predict_projection_seed",
        lambda symbol, market=None: {
            "symbol": symbol,
            "signal": "BUY",
            "confidence": 0.72,
            "expected_return": 0.08,
            "predicted_move": "+8.00%",
            "current_price": 95.0,
            "target_price": 102.6,
            "source": "transformer",
            "architecture": "fusion",
        },
    )

    async def _anchor(symbol, timeframe):
        assert symbol == "AAA.JK"
        assert timeframe == "1h"
        return {"time": 1710000000.0, "price": 100.0}

    monkeypatch.setattr(frontend_routes, "_resolve_latest_candle_anchor", _anchor)

    payload = asyncio.run(frontend_routes.get_ai_projection("aaa", timeframe="1h", horizon=6))

    assert payload.symbol == "AAA.JK"
    assert payload.timeframe == "1h"
    assert payload.horizon == 6
    assert payload.source == "transformer"
    assert payload.currentPrice == 100.0
    assert len(payload.projection) == 6
    assert payload.projection[0].time == 1710000000 + 3600
    assert payload.projection[-1].time == 1710000000 + (6 * 3600)
    assert payload.projection[-1].value > payload.currentPrice


def test_get_ai_projection_validates_timeframe_and_clamps_horizon(monkeypatch):
    monkeypatch.setattr(
        frontend_routes,
        "_predict_projection_seed",
        lambda symbol, market=None: {
            "symbol": symbol,
            "signal": "HOLD",
            "confidence": 0.5,
            "expected_return": 0.0,
            "predicted_move": "+0.00%",
            "current_price": 100.0,
            "target_price": 100.0,
            "source": "fallback",
            "architecture": None,
        },
    )

    async def _no_anchor(symbol, timeframe):
        return None

    monkeypatch.setattr(frontend_routes, "_resolve_latest_candle_anchor", _no_anchor)

    with pytest.raises(frontend_routes.HTTPException) as exc_info:
        asyncio.run(frontend_routes.get_ai_projection("BBCA.JK", timeframe="10m", horizon=16))
    assert exc_info.value.status_code == 400

    payload = asyncio.run(frontend_routes.get_ai_projection("BBCA.JK", timeframe="1d", horizon=999))
    assert payload.horizon == 120
    assert len(payload.projection) == 120


def test_get_ai_regime_status_returns_persisted_snapshot(monkeypatch):
    snapshot = {
        "regime": "BULL",
        "confidence": 0.83,
        "primaryAgent": "bull_agent",
        "strategyProfile": "momentum_breakout",
        "riskMultiplier": 1.0,
        "asOf": "2026-01-01T00:00:00",
    }

    monkeypatch.setattr(
        frontend_routes._state_store,
        "get_regime_state",
        lambda defaults: snapshot,
    )

    payload = asyncio.run(frontend_routes.get_ai_regime_status())
    assert payload["regime"] == "BULL"
    assert payload["primaryAgent"] == "bull_agent"


def test_resolve_regime_route_persists_transition_log(monkeypatch):
    captured = {"state": None, "logs": []}

    monkeypatch.setattr(
        frontend_routes._state_store,
        "get_regime_state",
        lambda defaults: {"regime": "BEAR"},
    )

    def _fake_set_regime_state(payload):
        captured["state"] = dict(payload)
        return dict(payload)

    monkeypatch.setattr(frontend_routes._state_store, "set_regime_state", _fake_set_regime_state)
    monkeypatch.setattr(
        frontend_routes._state_store,
        "append_ai_log",
        lambda **kwargs: captured["logs"].append(kwargs),
    )

    prices = np.linspace(100.0, 220.0, 64)
    df = pd.DataFrame(
        {
            "symbol": ["AAA.JK"] * len(prices),
            "last_price": prices,
        }
    )

    route = frontend_routes._resolve_regime_route(df, ["AAA.JK"])

    assert route is not None
    assert captured["state"] is not None
    assert captured["state"]["regime"] == "BULL"
    assert len(captured["logs"]) == 1
    assert captured["logs"][0]["event_type"] == "regime_transition"
