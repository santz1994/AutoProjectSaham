"""Projection learning state management for persistent model calibration.

Extracted from frontend_routes.py as part of Phase 1.5 modularisation wave.
Handles:
- CSV row counting / dataset path resolution
- Projection learning state persistence (JSON file)
- Prediction adjustment heuristics (_apply_projection_learning)
- Adaptive sort utility
"""

from __future__ import annotations

import csv
import os
from datetime import datetime, timedelta
from threading import Lock
from typing import Any, Callable, Dict, List, Optional, Tuple

from src.utils.datetime_utils import utcnow

__all__ = [
    "ProjectionLearningService",
]


class ProjectionLearningService:
    """Stateful projection learning helper extracted from frontend routes.

    All mutable state (``_projection_learning_state`` dict and
    ``_projection_learning_loaded`` flag) is encapsulated inside the
    instance, eliminating reliance on module-level globals.
    """

    def __init__(
        self,
        get_project_root_fn: Callable[[], str],
        logger: Optional[Any] = None,
    ) -> None:
        self._get_project_root = get_project_root_fn
        self._logger = logger
        self._state: Dict[str, Any] = {}
        self._loaded = False
        self._lock = Lock()

    # ------------------------------------------------------------------
    # Path helpers
    # ------------------------------------------------------------------

    def _projection_learning_state_path(self) -> str:
        return os.path.join(self._get_project_root(), "data", "projection_learning_state.json")

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _ensure_loaded(self) -> None:
        if self._loaded:
            return
        with self._lock:
            if self._loaded:
                return
            state_path = self._projection_learning_state_path()
            try:
                if os.path.exists(state_path):
                    import json
                    with open(state_path, encoding="utf-8") as fh:
                        self._state = json.load(fh)
            except Exception as exc:
                if self._logger:
                    self._logger.warning("Failed to load projection learning state: %s", exc)
            self._loaded = True

    def persist(self) -> None:
        if not self._loaded:
            return
        state_path = self._projection_learning_state_path()
        try:
            import json
            os.makedirs(os.path.dirname(state_path), exist_ok=True)
            with open(state_path, "w", encoding="utf-8") as fh:
                json.dump(self._state, fh, indent=2, default=str)
        except Exception as exc:
            if self._logger:
                self._logger.warning("Failed to persist projection learning state: %s", exc)

    # ------------------------------------------------------------------
    # Key helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _key(symbol: str, timeframe: str) -> str:
        normalized_tf = timeframe or "24h"
        return f"{str(symbol).strip().upper()}|{normalized_tf}"

    @staticmethod
    def _return_direction(value: float, epsilon: float = 0.0005) -> int:
        if value > epsilon:
            return 1
        if value < -epsilon:
            return -1
        return 0

    @staticmethod
    def _safe_float(value: Any, default: Optional[float] = 0.0) -> Optional[float]:
        if value is None:
            return default
        try:
            result = float(value)
            if result != result:
                return default
            return result
        except (TypeError, ValueError):
            return default

    # ------------------------------------------------------------------
    # Core learning
    # ------------------------------------------------------------------

    def apply_projection_learning(
        self,
        symbol: str,
        timeframe: str,
        projection_data: Dict[str, Any],
        *,
        learning_rate: float = 0.25,
        min_history_for_adjustment: int = 5,
        window: int = 5,
    ) -> Tuple[Dict[str, Any], float]:
        self._ensure_loaded()

        key = self._key(symbol, timeframe)
        predicted_return = self._safe_float(
            projection_data.get("predicted_return"),
            default=0.0,
        ) or 0.0

        direction = self._return_direction(predicted_return)
        symbol_state: Dict[str, Any] = self._state.get(key)
        if not symbol_state:
            symbol_state = {
                "samples": 0,
                "error_sum": 0.0,
                "abs_error_sum": 0.0,
                "last_actual_return": 0.0,
                "last_predicted_return": 0.0,
                "last_update": None,
                "history": [],
            }
            self._state[key] = symbol_state

        symbol_state["samples"] = int(symbol_state.get("samples", 0)) + 1
        symbol_state["last_predicted_return"] = predicted_return
        symbol_state["last_update"] = utcnow().isoformat()

        projection_data["learning_key"] = key
        projection_data["learning_samples"] = symbol_state["samples"]

        history = symbol_state.setdefault("history", [])
        history.append(
            {
                "predicted_return": predicted_return,
                "direction": direction,
                "timestamp": symbol_state["last_update"],
            }
        )
        symbol_state["history"] = history[-50:]

        history_adjustment = 0.0
        if len(history) >= window:
            recent = history[-window:]
            direction_counts: Dict[int, int] = {}
            for item in recent:
                item_direction = int(item.get("direction", 0))
                direction_counts[item_direction] = direction_counts.get(item_direction, 0) + 1

            dominant_direction = max(direction_counts, key=lambda k: direction_counts[k])
            dominant_ratio = direction_counts[dominant_direction] / float(window)

            if dominant_ratio >= 0.6:
                smoothing_base = 1.0 - (1.0 / window)
                smoothed_ratio = smoothing_base * dominant_ratio + (1.0 - smoothing_base)
                sign = 1.0 if dominant_direction >= 0 else -1.0
                history_adjustment = sign * smoothed_ratio * 0.12
                history_adjustment = max(-0.15, min(history_adjustment, 0.15))
                projection_data["learning_bias_source"] = "recent_pattern"

        next_predicted = predicted_return + history_adjustment
        if len(history) >= min_history_for_adjustment:
            symbol_state["last_actual_return"] = next_predicted

        projection_data["predicted_return"] = next_predicted
        projection_data["learning_adjustment"] = history_adjustment

        self.persist()

        confidence = float(projection_data.get("confidence", 0.0) or 0.0)
        boosted_confidence = confidence + (abs(predicted_return) / 2.0) + abs(history_adjustment)
        return projection_data, min(boosted_confidence, 1.0)

    # ------------------------------------------------------------------
    # Adaptive sort
    # ------------------------------------------------------------------

    @staticmethod
    def adaptive_sort(
        items: List[Any],
        key_name: str,
        reverse: bool = False,
    ) -> List[Any]:
        data = list(items)
        if len(data) <= 1:
            return data

        def _to_comparable(item: Any) -> Tuple[int, float, float, float, str]:
            value = item.get(key_name) if isinstance(item, dict) else getattr(item, key_name, None)
            try:
                numeric = float(value) if value is not None else float("-inf")
            except (TypeError, ValueError):
                numeric = float("-inf")

            first_price = None
            last_price = None
            if isinstance(item, dict):
                first_price = item.get("first_target_price")
                last_price = item.get("last_target_price")

            try:
                first_price_numeric = float(first_price) if first_price is not None else float("-inf")
            except (TypeError, ValueError):
                first_price_numeric = float("-inf")

            try:
                last_price_numeric = float(last_price) if last_price is not None else float("-inf")
            except (TypeError, ValueError):
                last_price_numeric = float("-inf")

            label_value = ""
            if isinstance(item, dict):
                label_value = str(item.get("label") or item.get("symbol") or "")
            else:
                label_value = str(getattr(item, "label", None) or getattr(item, "symbol", "") or "")

            isnan = 0 if numeric == numeric and numeric != float("inf") and numeric != float("-inf") else 1
            return (isnan, numeric, first_price_numeric, last_price_numeric, label_value.lower())

        try:
            from functools import cmp_to_key

            def _compare(lhs: Any, rhs: Any) -> int:
                lval = _to_comparable(lhs)
                rval = _to_comparable(rhs)
                if lval < rval:
                    return -1
                if lval > rval:
                    return 1
                return 0

            comparison = _compare
            if reverse:
                def _reverse_compare(lhs: Any, rhs: Any) -> int:
                    return _compare(rhs, lhs)
                comparison = _reverse_compare

            return sorted(data, key=cmp_to_key(comparison))
        except TypeError:
            return data

    # ------------------------------------------------------------------
    # State accessors (for testing / serialization)
    # ------------------------------------------------------------------

    @property
    def state(self) -> Dict[str, Any]:
        return self._state

    @property
    def loaded(self) -> bool:
        return self._loaded