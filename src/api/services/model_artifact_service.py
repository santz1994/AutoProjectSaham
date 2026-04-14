"""Model artifact discovery and metadata helpers for API layer."""

from __future__ import annotations

import json
import os
from datetime import datetime
from typing import Any, Dict, Optional


def _default_project_root() -> str:
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))


def _safe_float(value: Any, default: Optional[float] = 0.0) -> Optional[float]:
    try:
        parsed = float(value)
    except Exception:
        return default
    if parsed != parsed:
        return default
    if parsed in (float("inf"), float("-inf")):
        return default
    return parsed


def is_within_path(candidate_path: str, root_path: str) -> bool:
    try:
        candidate_abs = os.path.abspath(candidate_path)
        root_abs = os.path.abspath(root_path)
        return os.path.commonpath([candidate_abs, root_abs]) == root_abs
    except Exception:
        return False


def coerce_model_path(project_root: str, model_path: Optional[str]) -> Optional[str]:
    if model_path is None:
        return None

    raw = str(model_path).strip()
    if not raw:
        return None

    normalized = raw.replace("\\", os.sep).replace("/", os.sep)
    if os.path.isabs(normalized):
        candidate = os.path.normpath(normalized)
    else:
        candidate = os.path.normpath(os.path.join(project_root, normalized))

    if not is_within_path(candidate, project_root):
        return None
    return candidate


def load_json_if_exists(path: str) -> Optional[Dict[str, Any]]:
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
            return payload if isinstance(payload, dict) else None
    except Exception:
        return None


def artifact_meta(
    project_root: str,
    abs_path: str,
    architecture: Optional[str],
    source: str,
    score: Optional[float],
    accuracy: Optional[float] = None,
) -> Optional[Dict[str, Any]]:
    if not abs_path or (not os.path.exists(abs_path)):
        return None

    modified_ts = os.path.getmtime(abs_path)
    rel_path = os.path.relpath(abs_path, project_root).replace("\\", "/")
    return {
        "path": abs_path,
        "artifact": rel_path,
        "mtime": modified_ts,
        "lastTrainedAt": datetime.fromtimestamp(modified_ts).isoformat(),
        "architecture": architecture,
        "source": source,
        "score": float(score) if score is not None else None,
        "accuracy": float(accuracy) if accuracy is not None else None,
    }


def resolve_best_walk_forward_artifact(project_root: str) -> Optional[Dict[str, Any]]:
    report_path = os.path.join(project_root, "models", "transformers", "walk_forward_report.json")
    report = load_json_if_exists(report_path)
    if not report:
        return None

    results = report.get("results")
    if not isinstance(results, dict):
        return None

    best_meta = None
    best_rank = None

    for architecture, payload in results.items():
        if not isinstance(payload, dict):
            continue
        folds = payload.get("results")
        if not isinstance(folds, list):
            continue

        for fold in folds:
            if not isinstance(fold, dict):
                continue
            if fold.get("status") != "ok":
                continue

            model_path = coerce_model_path(project_root, fold.get("model_path"))
            if not model_path:
                continue

            metrics = fold.get("metrics") or {}
            if not isinstance(metrics, dict):
                metrics = {}
            score = metrics.get("f1_macro")
            accuracy = metrics.get("accuracy")
            meta = artifact_meta(
                project_root,
                model_path,
                architecture=str(architecture).lower(),
                source="walk_forward",
                score=_safe_float(score, default=None) if score is not None else None,
                accuracy=_safe_float(accuracy, default=None) if accuracy is not None else None,
            )
            if not meta:
                continue

            rank = (
                float(meta["score"]) if meta.get("score") is not None else float("-inf"),
                float(meta["accuracy"]) if meta.get("accuracy") is not None else float("-inf"),
                float(meta.get("mtime") or 0.0),
            )
            if best_rank is None or rank > best_rank:
                best_rank = rank
                best_meta = meta

    return best_meta


def resolve_best_baseline_artifact(project_root: str) -> Optional[Dict[str, Any]]:
    report_path = os.path.join(project_root, "models", "transformers", "baseline_report.json")
    report = load_json_if_exists(report_path)
    if not report:
        return None

    results = report.get("results")
    if not isinstance(results, dict):
        return None

    best_meta = None
    best_rank = None

    for architecture, payload in results.items():
        if not isinstance(payload, dict):
            continue

        model_path = coerce_model_path(project_root, payload.get("model_path"))
        if not model_path:
            continue

        metrics = payload.get("metrics") or {}
        if not isinstance(metrics, dict):
            metrics = {}
        score = metrics.get("f1_macro")
        accuracy = metrics.get("accuracy")
        meta = artifact_meta(
            project_root,
            model_path,
            architecture=str(architecture).lower(),
            source="baseline",
            score=_safe_float(score, default=None) if score is not None else None,
            accuracy=_safe_float(accuracy, default=None) if accuracy is not None else None,
        )
        if not meta:
            continue

        rank = (
            float(meta["score"]) if meta.get("score") is not None else float("-inf"),
            float(meta["accuracy"]) if meta.get("accuracy") is not None else float("-inf"),
            float(meta.get("mtime") or 0.0),
        )
        if best_rank is None or rank > best_rank:
            best_rank = rank
            best_meta = meta

    return best_meta


def resolve_latest_transformer_artifact(project_root: str) -> Optional[Dict[str, Any]]:
    transformers_dir = os.path.join(project_root, "models", "transformers")
    if not os.path.isdir(transformers_dir):
        return None

    latest_path = None
    latest_ts = None
    for root, _, files in os.walk(transformers_dir):
        for name in files:
            if not name.lower().endswith(".pt"):
                continue
            path = os.path.join(root, name)
            modified_ts = os.path.getmtime(path)
            if latest_ts is None or modified_ts > latest_ts:
                latest_ts = modified_ts
                latest_path = path

    if not latest_path:
        return None

    arch = None
    basename = os.path.basename(latest_path).lower()
    if "fusion" in basename:
        arch = "fusion"
    elif "patchtst" in basename:
        arch = "patchtst"
    elif "mtst" in basename:
        arch = "mtst"
    elif "tft" in basename:
        arch = "tft"

    return artifact_meta(
        project_root,
        latest_path,
        architecture=arch,
        source="latest_pt",
        score=None,
        accuracy=None,
    )


def resolve_best_transformer_artifact(project_root: Optional[str] = None) -> Optional[Dict[str, Any]]:
    root = project_root or _default_project_root()
    candidates = [
        resolve_best_walk_forward_artifact(root),
        resolve_best_baseline_artifact(root),
        resolve_latest_transformer_artifact(root),
    ]
    valid_candidates = [candidate for candidate in candidates if candidate]
    if not valid_candidates:
        return None

    def _candidate_rank(item: Dict[str, Any]) -> tuple[float, float, float]:
        score = item.get("score")
        accuracy = item.get("accuracy")
        return (
            float(score) if score is not None else float("-inf"),
            float(accuracy) if accuracy is not None else float("-inf"),
            float(item.get("mtime") or 0.0),
        )

    scored_candidates = [candidate for candidate in valid_candidates if candidate.get("score") is not None]
    if scored_candidates:
        return max(scored_candidates, key=_candidate_rank)

    return max(valid_candidates, key=lambda item: float(item.get("mtime") or 0.0))


def get_latest_model_artifact(project_root: Optional[str] = None) -> Dict[str, Any]:
    root = project_root or _default_project_root()

    transformer_artifact = resolve_best_transformer_artifact(root)
    if transformer_artifact:
        return {
            "artifact": transformer_artifact.get("artifact"),
            "lastTrainedAt": transformer_artifact.get("lastTrainedAt"),
            "architecture": transformer_artifact.get("architecture"),
            "source": transformer_artifact.get("source"),
            "score": transformer_artifact.get("score"),
        }

    models_dir = os.path.join(root, "models")
    candidates = ["model.joblib", "ensemble_test.joblib"]
    latest_name = None
    latest_ts = None

    for name in candidates:
        path = os.path.join(models_dir, name)
        if not os.path.exists(path):
            continue
        modified_ts = os.path.getmtime(path)
        if latest_ts is None or modified_ts > latest_ts:
            latest_ts = modified_ts
            latest_name = name

    if latest_name is None or latest_ts is None:
        return {
            "artifact": None,
            "lastTrainedAt": None,
            "architecture": None,
            "source": None,
            "score": None,
        }

    return {
        "artifact": latest_name,
        "lastTrainedAt": datetime.fromtimestamp(latest_ts).isoformat(),
        "architecture": "legacy",
        "source": "legacy_joblib",
        "score": None,
    }
