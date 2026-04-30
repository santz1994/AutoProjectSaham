"""Helpers for projection seed normalization and projection curve generation."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from src.api.config.frontend_constants import timeframe_seconds
from src.api.schemas.frontend import AIProjectionPoint, Signal
from src.api.services.market_data_service import normalize_symbol_input


def _safe_float(value: Any, default: Optional[float] = 0.0) -> Optional[float]:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    if parsed != parsed:
        return default
    if parsed in (float("inf"), float("-inf")):
        return default
    return parsed


def parse_predicted_move(predicted_move: Any) -> Optional[float]:
    raw = str(predicted_move or "").strip().replace("%", "")
    if not raw:
        return None
    parsed = _safe_float(raw, default=None)
    if parsed is None:
        return None
    return float(parsed) / 100.0


def signal_to_projection_seed(signal: Signal, source: str) -> Dict[str, Any]:
    current_price = _safe_float(signal.currentPrice, default=0.0) or 0.0
    target_price = _safe_float(signal.targetPrice, default=current_price) or current_price

    expected_return = 0.0
    if current_price > 0:
        expected_return = (target_price / current_price) - 1.0
    elif current_price <= 0:
        parsed_move = parse_predicted_move(signal.predictedMove)
        if parsed_move is not None:
            expected_return = parsed_move

    return {
        "symbol": normalize_symbol_input(signal.symbol),
        "signal": signal.signal,
        "reason": str(signal.reason or "Model produced a directional signal."),
        "confidence": float(max(0.0, min(1.0, signal.confidence))),
        "model_confidence": float(max(0.0, min(1.0, signal.confidence))),
        "expected_return": float(expected_return),
        "predicted_move": signal.predictedMove,
        "current_price": float(max(0.0, current_price)),
        "target_price": float(max(0.0, target_price)),
        "source": source,
    }


def resolve_timeframe_seconds(timeframe: str) -> int:
    normalized = str(timeframe or "").strip().lower()
    return timeframe_seconds.get(normalized, timeframe_seconds["1d"])


def build_projection_points(
    base_time: int,
    current_price: float,
    expected_return: float,
    timeframe: str,
    horizon: int,
) -> List[AIProjectionPoint]:
    safe_horizon = max(1, int(horizon))
    safe_price = float(max(0.01, current_price))
    interval_seconds = resolve_timeframe_seconds(timeframe)

    # Keep projected move bounded to avoid unstable extrapolation.
    bounded_return = float(max(-0.30, min(0.30, expected_return)))

    points: List[AIProjectionPoint] = []
    for step in range(1, safe_horizon + 1):
        fraction = step / safe_horizon
        smooth_fraction = (fraction * fraction) * (3.0 - (2.0 * fraction))
        projected_factor = 1.0 + (bounded_return * smooth_fraction)
        projected_factor = max(0.05, projected_factor)
        value = safe_price * projected_factor
        points.append(
            AIProjectionPoint(
                time=int(base_time + (step * interval_seconds)),
                value=float(round(value, 4)),
            )
        )

    return points
