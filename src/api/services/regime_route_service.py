"""Helpers for regime-route profile override and state persistence."""

from __future__ import annotations

import asyncio
from datetime import datetime
from types import SimpleNamespace
from typing import Any, Callable, Dict, List, Optional, Tuple


def normalize_strategy_profile_key(
    value: Any,
    *,
    profile_route_presets: Dict[str, Dict[str, Any]],
) -> Optional[str]:
    parsed = str(value or "").strip().lower()
    if not parsed:
        return None

    normalized = parsed.replace("-", "_").replace(" ", "_")
    alias_map = {
        "auto": None,
        "automatic": None,
        "none": None,
        "regime_router": None,
        "momentum": "momentum_breakout",
        "mean_reversion": "mean_reversion_swing",
        "mean_reversion_swing": "mean_reversion_swing",
        "rotation": "defensive_rotation",
        "defensive_rotation": "defensive_rotation",
        "momentum_breakout": "momentum_breakout",
    }
    resolved = alias_map.get(normalized, normalized)
    if resolved is None:
        return None
    if resolved not in profile_route_presets:
        return None
    return str(resolved)


def resolve_manual_strategy_profile(
    *,
    state_store: Any,
    default_user_settings: Dict[str, Any],
    profile_route_presets: Dict[str, Dict[str, Any]],
) -> Optional[str]:
    try:
        settings = state_store.get_user_settings(default_user_settings)
    except Exception:
        return None

    return normalize_strategy_profile_key(
        settings.get("aiManualStrategyProfile"),
        profile_route_presets=profile_route_presets,
    )


def apply_strategy_profile_override_to_route(
    route: Any,
    *,
    profile_route_presets: Dict[str, Dict[str, Any]],
    resolve_manual_strategy_profile_fn: Callable[[], Optional[str]],
    manual_profile: Optional[str] = None,
) -> Tuple[Any, Optional[str]]:
    profile = normalize_strategy_profile_key(
        manual_profile,
        profile_route_presets=profile_route_presets,
    )
    if profile is None:
        profile = resolve_manual_strategy_profile_fn()

    if profile is None:
        return route, None

    preset = profile_route_presets.get(profile) or {}
    return (
        SimpleNamespace(
            regime=str(getattr(route, "regime", "UNKNOWN")),
            confidence=float(max(0.0, min(1.0, getattr(route, "confidence", 0.0)))),
            primary_agent=str(
                preset.get("primaryAgent")
                or getattr(route, "primary_agent", "scalper_agent")
            ),
            strategy_profile=str(profile),
            risk_multiplier=float(
                preset.get("riskMultiplier", getattr(route, "risk_multiplier", 0.75))
            ),
            trend_return=float(getattr(route, "trend_return", 0.0)),
            volatility=float(max(0.0, getattr(route, "volatility", 0.0))),
            up_move_ratio=float(
                max(0.0, min(1.0, getattr(route, "up_move_ratio", 0.5)))
            ),
        ),
        profile,
    )


def sync_regime_profile_override(
    manual_profile_value: Any,
    *,
    state_store: Any,
    default_regime_state: Dict[str, Any],
    profile_route_presets: Dict[str, Dict[str, Any]],
) -> Dict[str, Any]:
    active_profile = normalize_strategy_profile_key(
        manual_profile_value,
        profile_route_presets=profile_route_presets,
    )
    current_regime = state_store.get_regime_state(default_regime_state)

    if active_profile is None:
        return state_store.set_regime_state(
            {
                **current_regime,
                "manualProfileOverride": False,
                "profileSource": "regime_router",
                "asOf": datetime.now().isoformat(),
            }
        )

    profile_preset = profile_route_presets.get(active_profile) or {}
    return state_store.set_regime_state(
        {
            **current_regime,
            "strategyProfile": active_profile,
            "primaryAgent": str(
                profile_preset.get("primaryAgent")
                or current_regime.get("primaryAgent")
                or "scalper_agent"
            ),
            "riskMultiplier": float(
                profile_preset.get("riskMultiplier", current_regime.get("riskMultiplier") or 0.75)
            ),
            "manualProfileOverride": True,
            "profileSource": "manual_override",
            "asOf": datetime.now().isoformat(),
        }
    )


def build_regime_state_payload(
    route: Any,
    symbols: Optional[List[str]],
    price_points: int,
    *,
    profile_route_presets: Dict[str, Dict[str, Any]],
    manual_profile_override: Optional[str] = None,
) -> Dict[str, Any]:
    active_manual_profile = normalize_strategy_profile_key(
        manual_profile_override,
        profile_route_presets=profile_route_presets,
    )
    active_profile = str(getattr(route, "strategy_profile", "mean_reversion_swing"))
    if active_manual_profile is not None:
        active_profile = active_manual_profile

    profile_preset = profile_route_presets.get(active_profile) or {}
    primary_agent = str(
        profile_preset.get("primaryAgent")
        or getattr(route, "primary_agent", "scalper_agent")
    )
    risk_multiplier = float(
        profile_preset.get("riskMultiplier", getattr(route, "risk_multiplier", 0.75))
    )

    return {
        "regime": str(getattr(route, "regime", "UNKNOWN")),
        "confidence": float(max(0.0, min(1.0, getattr(route, "confidence", 0.0)))),
        "primaryAgent": primary_agent,
        "strategyProfile": active_profile,
        "manualProfileOverride": active_manual_profile is not None,
        "profileSource": "manual_override" if active_manual_profile is not None else "regime_router",
        "riskMultiplier": risk_multiplier,
        "trendReturn": float(getattr(route, "trend_return", 0.0)),
        "volatility": float(max(0.0, getattr(route, "volatility", 0.0))),
        "upMoveRatio": float(max(0.0, min(1.0, getattr(route, "up_move_ratio", 0.5)))),
        "symbols": [str(item) for item in (symbols or [])[:5]],
        "pricePoints": int(max(0, int(price_points))),
        "asOf": datetime.now().isoformat(),
    }


def persist_regime_route(
    route: Any,
    symbols: Optional[List[str]],
    price_points: int,
    *,
    state_store: Any,
    default_regime_state: Dict[str, Any],
    profile_route_presets: Dict[str, Dict[str, Any]],
    emit_regime_transition_notification_fn: Callable[[str, str, Dict[str, Any]], Any],
    manual_profile_override: Optional[str] = None,
) -> None:
    try:
        previous_state = state_store.get_regime_state(default_regime_state)
        next_state = build_regime_state_payload(
            route,
            symbols,
            price_points,
            profile_route_presets=profile_route_presets,
            manual_profile_override=manual_profile_override,
        )
        saved_state = state_store.set_regime_state(next_state)

        previous_regime = str(previous_state.get("regime") or "UNKNOWN").upper()
        current_regime = str(saved_state.get("regime") or "UNKNOWN").upper()
        if (
            previous_regime not in {"", "UNKNOWN"}
            and current_regime not in {"", "UNKNOWN"}
            and previous_regime != current_regime
        ):
            is_major_transition = {previous_regime, current_regime} == {"BULL", "BEAR"}
            state_store.append_ai_log(
                level="warning" if is_major_transition else "info",
                event_type="regime_transition_major" if is_major_transition else "regime_transition",
                message=(
                    f"Major regime transition: {previous_regime} -> {current_regime}"
                    if is_major_transition
                    else f"Regime transition: {previous_regime} -> {current_regime}"
                ),
                payload={
                    "from": previous_regime,
                    "to": current_regime,
                    "majorTransition": is_major_transition,
                    "confidence": saved_state.get("confidence"),
                    "primaryAgent": saved_state.get("primaryAgent"),
                },
            )

            if is_major_transition:
                try:
                    loop = asyncio.get_running_loop()
                    loop.create_task(
                        emit_regime_transition_notification_fn(
                            previous_regime,
                            current_regime,
                            saved_state,
                        )
                    )
                except Exception:
                    pass
    except Exception:
        pass


def resolve_regime_route(
    df: Any,
    symbols: Optional[List[str]],
    *,
    extract_price_series_fn: Callable[[Any, Optional[List[str]]], List[float]],
    apply_strategy_profile_override_to_route_fn: Callable[[Any], Tuple[Any, Optional[str]]],
    persist_regime_route_fn: Callable[[Any, Optional[List[str]], int, Optional[str]], None],
) -> Optional[Any]:
    try:
        from src.ml.regime_router import classify_market_regime

        price_series = extract_price_series_fn(df, symbols)
        if not price_series:
            return None

        route = classify_market_regime(price_series)
        route, active_manual_profile = apply_strategy_profile_override_to_route_fn(route)
        persist_regime_route_fn(
            route,
            symbols,
            len(price_series),
            active_manual_profile,
        )
        return route
    except Exception:
        return None
