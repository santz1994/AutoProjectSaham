"""Persistent model registry for AutoSaham.

This lightweight registry tracks model artifacts, metrics, and active model
selection in a JSON file under data/. It is intentionally file-based to keep
runtime dependencies minimal while enabling reproducible model lifecycle.
"""
from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
DEFAULT_REGISTRY_PATH = os.path.join(PROJECT_ROOT, "data", "model_registry.json")


_registry_lock = threading.RLock()


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _to_float_or_none(value: Any) -> Optional[float]:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _normalize_model_path(model_path: str) -> str:
    absolute = os.path.abspath(str(model_path or "").strip())
    if not absolute:
        raise ValueError("model_path is required")

    try:
        common = os.path.commonpath([absolute, PROJECT_ROOT])
        if common == PROJECT_ROOT:
            return os.path.relpath(absolute, PROJECT_ROOT).replace("\\", "/")
    except Exception:
        pass
    return absolute.replace("\\", "/")


def _empty_registry() -> Dict[str, Any]:
    return {
        "version": 1,
        "updatedAt": _utc_now_iso(),
        "activeModelId": None,
        "models": [],
    }


def _load_registry(registry_path: str) -> Dict[str, Any]:
    if not os.path.exists(registry_path):
        return _empty_registry()

    try:
        with open(registry_path, "r", encoding="utf-8") as file:
            payload = json.load(file)
        if not isinstance(payload, dict):
            return _empty_registry()
        payload.setdefault("version", 1)
        payload.setdefault("updatedAt", _utc_now_iso())
        payload.setdefault("activeModelId", None)
        payload.setdefault("models", [])
        if not isinstance(payload.get("models"), list):
            payload["models"] = []
        return payload
    except Exception:
        return _empty_registry()


def _save_registry(registry_path: str, payload: Dict[str, Any]) -> None:
    payload["updatedAt"] = _utc_now_iso()
    os.makedirs(os.path.dirname(registry_path) or ".", exist_ok=True)
    with open(registry_path, "w", encoding="utf-8") as file:
        json.dump(payload, file, indent=2, ensure_ascii=True)


def register_model_artifact(
    model_path: str,
    *,
    registry_path: str = DEFAULT_REGISTRY_PATH,
    source: str = "trainer",
    framework: str = "sklearn",
    architecture: str = "tabular_classifier",
    metrics: Optional[Dict[str, Any]] = None,
    tags: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Register or update a model artifact in the registry."""
    normalized_path = _normalize_model_path(model_path)
    absolute_model_path = os.path.join(PROJECT_ROOT, normalized_path)
    if not os.path.isabs(model_path):
        absolute_model_path = os.path.abspath(os.path.join(PROJECT_ROOT, normalized_path))

    file_size = 0
    mtime = None
    if os.path.exists(absolute_model_path):
        try:
            stat_info = os.stat(absolute_model_path)
            file_size = int(stat_info.st_size)
            mtime = datetime.fromtimestamp(stat_info.st_mtime, tz=timezone.utc).isoformat()
        except Exception:
            pass

    payload_metrics = metrics.copy() if isinstance(metrics, dict) else {}
    if "roc_auc" in payload_metrics:
        payload_metrics["roc_auc"] = _to_float_or_none(payload_metrics.get("roc_auc"))

    now_iso = _utc_now_iso()

    with _registry_lock:
        registry = _load_registry(registry_path)
        models = registry.get("models", [])

        existing = None
        for item in models:
            if str(item.get("path")) == normalized_path:
                existing = item
                break

        if existing is None:
            next_index = len(models) + 1
            existing = {
                "id": f"model-{next_index:05d}",
                "path": normalized_path,
                "createdAt": now_iso,
            }
            models.append(existing)

        existing.update(
            {
                "path": normalized_path,
                "source": str(source or "trainer"),
                "framework": str(framework or "sklearn"),
                "architecture": str(architecture or "tabular_classifier"),
                "metrics": payload_metrics,
                "tags": [str(tag) for tag in (tags or []) if str(tag).strip()],
                "sizeBytes": int(file_size),
                "modifiedAt": mtime or now_iso,
                "lastRegisteredAt": now_iso,
            }
        )

        if not registry.get("activeModelId"):
            registry["activeModelId"] = existing.get("id")

        registry["models"] = models
        _save_registry(registry_path, registry)

        return dict(existing)


def list_registered_models(
    *,
    limit: int = 100,
    registry_path: str = DEFAULT_REGISTRY_PATH,
) -> List[Dict[str, Any]]:
    """Return registry models sorted by registration time descending."""
    with _registry_lock:
        registry = _load_registry(registry_path)

    models = registry.get("models", [])
    models_sorted = sorted(
        models,
        key=lambda item: str(item.get("lastRegisteredAt") or item.get("createdAt") or ""),
        reverse=True,
    )
    safe_limit = max(1, min(int(limit or 100), 500))
    return [dict(item) for item in models_sorted[:safe_limit]]


def get_registry_snapshot(
    *,
    registry_path: str = DEFAULT_REGISTRY_PATH,
    limit: int = 100,
) -> Dict[str, Any]:
    with _registry_lock:
        registry = _load_registry(registry_path)

    models = list_registered_models(limit=limit, registry_path=registry_path)
    return {
        "version": registry.get("version", 1),
        "updatedAt": registry.get("updatedAt"),
        "activeModelId": registry.get("activeModelId"),
        "models": models,
    }


def get_active_model(
    *,
    registry_path: str = DEFAULT_REGISTRY_PATH,
) -> Optional[Dict[str, Any]]:
    with _registry_lock:
        registry = _load_registry(registry_path)

    active_id = str(registry.get("activeModelId") or "").strip()
    if not active_id:
        return None

    for item in registry.get("models", []):
        if str(item.get("id")) == active_id:
            return dict(item)
    return None


def set_active_model(
    model_id: str,
    *,
    registry_path: str = DEFAULT_REGISTRY_PATH,
) -> Dict[str, Any]:
    normalized = str(model_id or "").strip()
    if not normalized:
        raise ValueError("model_id is required")

    with _registry_lock:
        registry = _load_registry(registry_path)
        matched = None
        for item in registry.get("models", []):
            if str(item.get("id")) == normalized:
                matched = item
                break

        if matched is None:
            raise ValueError("model_id not found in registry")

        registry["activeModelId"] = normalized
        _save_registry(registry_path, registry)

    return dict(matched)


def get_best_model(
    *,
    metric_key: str = "roc_auc",
    registry_path: str = DEFAULT_REGISTRY_PATH,
) -> Optional[Dict[str, Any]]:
    models = list_registered_models(limit=500, registry_path=registry_path)
    best_item = None
    best_score = None

    for item in models:
        metrics = item.get("metrics") if isinstance(item.get("metrics"), dict) else {}
        score = _to_float_or_none(metrics.get(metric_key))
        if score is None:
            continue
        if best_score is None or score > best_score:
            best_score = score
            best_item = item

    return dict(best_item) if best_item else None
