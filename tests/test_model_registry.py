from pathlib import Path

from src.ml.model_registry import (
    get_active_model,
    get_best_model,
    get_registry_snapshot,
    register_model_artifact,
    set_active_model,
)


def test_model_registry_registers_and_selects_best(tmp_path):
    registry_path = tmp_path / "model_registry.json"

    model_a = tmp_path / "model_a.joblib"
    model_b = tmp_path / "model_b.joblib"
    model_a.write_bytes(b"a")
    model_b.write_bytes(b"b")

    a = register_model_artifact(
        str(model_a),
        registry_path=str(registry_path),
        metrics={"roc_auc": 0.61},
        tags=["baseline"],
    )
    b = register_model_artifact(
        str(model_b),
        registry_path=str(registry_path),
        metrics={"roc_auc": 0.74},
        tags=["candidate"],
    )

    snapshot = get_registry_snapshot(registry_path=str(registry_path))
    assert len(snapshot["models"]) == 2

    best = get_best_model(registry_path=str(registry_path))
    assert best is not None
    assert best["id"] == b["id"]

    selected = set_active_model(a["id"], registry_path=str(registry_path))
    assert selected["id"] == a["id"]

    active = get_active_model(registry_path=str(registry_path))
    assert active is not None
    assert active["id"] == a["id"]


def test_model_registry_handles_missing_metric(tmp_path):
    registry_path = tmp_path / "model_registry.json"
    model_path = tmp_path / "model.joblib"
    model_path.write_bytes(b"x")

    register_model_artifact(
        str(model_path),
        registry_path=str(registry_path),
        metrics={"accuracy": 0.9},
    )

    best = get_best_model(metric_key="roc_auc", registry_path=str(registry_path))
    assert best is None
