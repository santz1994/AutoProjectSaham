"""
Additional API routes for AutoSaham frontend integration.
Contains endpoints for portfolio, bot status, signals, strategies, trades, and market data.
"""

import asyncio
import base64
import binascii
import csv
import hashlib
import hmac
import json
import math
import os
from functools import partial
from types import SimpleNamespace
from threading import Lock
from fastapi import APIRouter, HTTPException, Request
from typing import Optional, List, Dict, Any, Tuple
from datetime import datetime, timedelta

from src.api.auth import get_session_context, get_user_from_token
from src.api.config.frontend_constants import (
    available_broker_providers as _available_broker_providers,
    crypto_symbols as _CRYPTO_SYMBOLS,
    default_broker_connection as _default_broker_connection,
    default_broker_feature_flags as _default_broker_feature_flags,
    default_regime_state as _default_regime_state,
    default_system_control as _default_system_control,
    default_user_settings as _default_user_settings,
    forex_symbols as _FOREX_SYMBOLS,
    institutional_broker_ids as _INSTITUTIONAL_BROKER_IDS,
    market_aliases as _MARKET_ALIASES,
    market_news_fallback as _MARKET_NEWS_FALLBACK,
    profile_route_presets as _PROFILE_ROUTE_PRESETS,
    strategy_profile_by_type as _STRATEGY_PROFILE_BY_TYPE,
    symbol_name_map as _SYMBOL_NAME_MAP,
    symbol_sector_map as _SYMBOL_SECTOR_MAP,
    timeframe_seconds as _TIMEFRAME_SECONDS,
)
from src.api.quota_usage import (
    get_quota_usage_snapshot,
    list_quota_usage_snapshots,
    resolve_tier_from_role,
)
from src.api.state_store import SecureAppStateStore
from src.api.schemas.frontend import (
    Activity,
    AILogPayload,
    AIProjectionPoint,
    AIProjectionResponse,
    BotStatus,
    BrokerConnectPayload,
    BrokerFeatureFlag,
    BrokerFeatureFlagUpdatePayload,
    BrokerProvider,
    ExecutionOrderPayload,
    KillSwitchPayload,
    MarketMover,
    MarketMoversResponse,
    MarketSentiment,
    Portfolio,
    PortfolioPosition,
    PortfolioHealth,
    SectorData,
    Signal,
    StateMigrationPayload,
    Strategy,
    Trade,
    UserSettings,
)
from src.api.services.projection_response_service import (
    aggregate_news_sentiment as _aggregate_news_sentiment,
    build_ai_rationale as _build_ai_rationale,
    build_generated_news_context as _build_generated_news_context,
    confidence_label as _confidence_label,
)
from src.api.services.market_data_service import (
    detect_market_from_symbol as _detect_market_from_symbol,
    fetch_global_market_news as _fetch_global_market_news,
    is_crypto_symbol as _is_crypto_symbol,
    is_forex_symbol as _is_forex_symbol,
    is_supported_market_symbol as _is_supported_market_symbol,
    normalize_market_input as _normalize_market_input,
    normalize_market_input_strict as _normalize_market_input_strict,
    normalize_symbol_input as _normalize_symbol_input,
    symbol_aliases as _symbol_aliases,
    symbol_base as _symbol_base,
    symbols_match as _symbols_match,
)
from src.api.services.model_artifact_service import (
    artifact_meta as _artifact_meta,
    coerce_model_path as _coerce_model_path,
    get_latest_model_artifact as _get_latest_model_artifact,
    is_within_path as _is_within_path,
    load_json_if_exists as _load_json_if_exists,
    resolve_best_baseline_artifact as _resolve_best_baseline_artifact,
    resolve_best_transformer_artifact as _resolve_best_transformer_artifact,
    resolve_best_walk_forward_artifact as _resolve_best_walk_forward_artifact,
    resolve_latest_transformer_artifact as _resolve_latest_transformer_artifact,
)
from src.brokers.paper_adapter import PaperBrokerAdapter

router = APIRouter(prefix="/api", tags=["frontend"])

_state_store = SecureAppStateStore()
_state_store.ensure_feature_flags(_default_broker_feature_flags)
_state_store.ensure_seed_ai_logs(
    [
        {
            "level": "info",
            "eventType": "ml_boot",
            "message": "AI services initialized and waiting for market ticks.",
            "payload": {"component": "ml_service"},
            "timestamp": (datetime.now() - timedelta(minutes=18)).isoformat(),
        },
        {
            "level": "info",
            "eventType": "feature_pipeline",
            "message": "Feature pipeline refreshed with latest Forex/Crypto market snapshot.",
            "payload": {"source": "dataset.csv"},
            "timestamp": (datetime.now() - timedelta(minutes=11)).isoformat(),
        },
        {
            "level": "warning",
            "eventType": "drift_watch",
            "message": "Drift monitor detected volatility shift on consumer sector basket.",
            "payload": {"sector": "consumer", "severity": "medium"},
            "timestamp": (datetime.now() - timedelta(minutes=5)).isoformat(),
        },
    ]
)
_state_store.get_regime_state(_default_regime_state)
_projection_notification_state: Dict[Tuple[str, str], str] = {}
_regime_notification_state: Dict[str, str] = {}

_transformer_runtime_cache: Dict[str, Any] = {
    "path": None,
    "mtime": None,
    "runtime": None,
}

_projection_learning_state: Dict[str, Any] = {}
_projection_learning_loaded = False
_projection_learning_lock = Lock()


def _count_csv_rows(csv_path: str) -> int:
    if not os.path.exists(csv_path):
        return 0

    with open(csv_path, "r", encoding="utf-8") as file:
        reader = csv.reader(file)
        count = -1  # exclude header row
        for count, _ in enumerate(reader):
            pass

    return max(0, count)


def _resolve_dataset_csv_path() -> str:
    """Resolve the most relevant dataset CSV path for AI overview metrics."""
    project_root = _get_project_root()
    candidates = [
        os.path.join(project_root, "data", "dataset", "dataset.csv"),
        os.path.join(project_root, "data", "dataset.csv"),
    ]

    for path in candidates:
        if os.path.exists(path):
            return path

    return candidates[0]


def _get_project_root() -> str:
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


def _projection_learning_state_path() -> str:
    return os.path.join(_get_project_root(), "data", "projection_learning_state.json")


def _ensure_projection_learning_state_loaded() -> None:
    global _projection_learning_loaded
    global _projection_learning_state

    if _projection_learning_loaded:
        return

    with _projection_learning_lock:
        if _projection_learning_loaded:
            return

        state_path = _projection_learning_state_path()
        loaded_state: Dict[str, Any] = {}
        if os.path.exists(state_path):
            try:
                with open(state_path, "r", encoding="utf-8") as file:
                    payload = json.load(file)
                if isinstance(payload, dict):
                    loaded_state = payload
            except Exception:
                loaded_state = {}

        _projection_learning_state = loaded_state
        _projection_learning_loaded = True


def _persist_projection_learning_state() -> None:
    _ensure_projection_learning_state_loaded()

    state_path = _projection_learning_state_path()
    state_dir = os.path.dirname(state_path)

    try:
        os.makedirs(state_dir, exist_ok=True)
        with _projection_learning_lock:
            snapshot = json.loads(json.dumps(_projection_learning_state))

        temp_path = f"{state_path}.tmp"
        with open(temp_path, "w", encoding="utf-8") as file:
            json.dump(snapshot, file, ensure_ascii=True)
        os.replace(temp_path, state_path)
    except Exception:
        return


def _safe_float(value: Any, default: Optional[float] = 0.0) -> Optional[float]:
    try:
        parsed = float(value)
    except Exception:
        return default
    if parsed != parsed:  # NaN
        return default
    if parsed in (float("inf"), float("-inf")):
        return default
    return parsed


def _projection_learning_key(symbol: str, timeframe: str) -> str:
    return f"{str(symbol or '').upper()}|{str(timeframe or '1d').lower()}"


def _return_direction(value: float, epsilon: float = 0.0005) -> int:
    if value > epsilon:
        return 1
    if value < -epsilon:
        return -1
    return 0


def _apply_projection_learning(
    symbol: str,
    timeframe: str,
    confidence: float,
    expected_return: float,
    anchor_time: int,
    anchor_price: float,
    horizon: int,
) -> Dict[str, Any]:
    _ensure_projection_learning_state_loaded()

    key = _projection_learning_key(symbol, timeframe)
    safe_confidence = float(max(0.0, min(1.0, confidence)))
    safe_expected = float(max(-0.30, min(0.30, expected_return)))
    safe_anchor_time = int(max(0, anchor_time))
    safe_anchor_price = float(max(0.01, anchor_price))
    safe_horizon = int(max(1, horizon))

    timeframe_seconds = int(_TIMEFRAME_SECONDS.get(str(timeframe).lower(), _TIMEFRAME_SECONDS["1d"]))
    evaluation_after_seconds = int(max(300, min(timeframe_seconds, 4 * 60 * 60)))
    now_ts = int(datetime.now().timestamp())

    with _projection_learning_lock:
        record = _projection_learning_state.get(key)
        if not isinstance(record, dict):
            record = {}

        reliability = float(max(0.30, min(0.98, _safe_float(record.get("reliability"), default=0.58) or 0.58)))
        observations = int(max(0, _safe_float(record.get("observations"), default=0.0) or 0.0))
        wins = int(max(0, _safe_float(record.get("wins"), default=0.0) or 0.0))
        losses = int(max(0, _safe_float(record.get("losses"), default=0.0) or 0.0))

        last_prediction = record.get("lastPrediction")
        if isinstance(last_prediction, dict):
            last_time = int(_safe_float(last_prediction.get("anchorTime"), default=0.0) or 0.0)
            last_price = _safe_float(last_prediction.get("anchorPrice"), default=None)
            last_expected = _safe_float(last_prediction.get("expectedReturn"), default=0.0) or 0.0
            last_eval_after = int(
                _safe_float(last_prediction.get("evaluationAfterSeconds"), default=float(evaluation_after_seconds))
                or evaluation_after_seconds
            )

            if (
                last_time > 0
                and last_price is not None
                and last_price > 0
                and now_ts >= (last_time + max(300, last_eval_after))
                and safe_anchor_price > 0
            ):
                actual_return = float((safe_anchor_price / float(last_price)) - 1.0)
                predicted_direction = _return_direction(float(last_expected))
                actual_direction = _return_direction(actual_return)

                direction_score = 1.0 if predicted_direction == actual_direction else 0.0
                if predicted_direction == 0 and abs(actual_return) <= 0.002:
                    direction_score = 1.0

                magnitude_error = abs(actual_return - float(last_expected))
                magnitude_score = float(max(0.0, 1.0 - min(1.0, magnitude_error / 0.08)))
                sample_score = float((0.72 * direction_score) + (0.28 * magnitude_score))

                reliability = float(max(0.30, min(0.98, (0.88 * reliability) + (0.12 * sample_score))))
                observations += 1

                if direction_score >= 0.99:
                    wins += 1
                else:
                    losses += 1

        sample_weight = float(min(0.28, 0.04 + (0.008 * min(observations, 30))))
        learning_boost = float((reliability - 0.50) * sample_weight)
        horizon_bias = float(max(-0.02, min(0.03, ((safe_horizon - 16) / 16.0) * 0.01)))
        calibrated_confidence = float(max(0.55, min(0.96, safe_confidence + learning_boost + horizon_bias)))

        _projection_learning_state[key] = {
            "symbol": str(symbol or "").upper(),
            "timeframe": str(timeframe or "1d").lower(),
            "reliability": round(reliability, 6),
            "observations": int(observations),
            "wins": int(wins),
            "losses": int(losses),
            "updatedAt": datetime.now().isoformat(),
            "lastPrediction": {
                "anchorTime": int(safe_anchor_time),
                "anchorPrice": float(safe_anchor_price),
                "expectedReturn": float(safe_expected),
                "horizon": int(safe_horizon),
                "evaluationAfterSeconds": int(evaluation_after_seconds),
            },
        }

    _persist_projection_learning_state()

    return {
        "calibratedConfidence": calibrated_confidence,
        "reliability": reliability,
        "observations": observations,
        "wins": wins,
        "losses": losses,
    }


def _adaptive_sort(items: List[Any], key_name: str, reverse: bool = False) -> List[Any]:
    total = len(items)
    if total <= 1:
        return list(items)

    output = list(items)
    if total <= 18:
        # Bubble sort is deterministic and lightweight for small collections.
        for idx in range(total):
            swapped = False
            for jdx in range(0, total - idx - 1):
                left = _safe_float(output[jdx].get(key_name), default=0.0) or 0.0
                right = _safe_float(output[jdx + 1].get(key_name), default=0.0) or 0.0
                needs_swap = left < right if reverse else left > right
                if needs_swap:
                    output[jdx], output[jdx + 1] = output[jdx + 1], output[jdx]
                    swapped = True
            if not swapped:
                break
        return output

    ranked = []
    for idx, item in enumerate(output):
        value = _safe_float(item.get(key_name), default=0.0) or 0.0
        ranked.append(((-value if reverse else value), idx, item))

    import heapq
    heapq.heapify(ranked)

    sorted_items = []
    while ranked:
        sorted_items.append(heapq.heappop(ranked)[2])
    return sorted_items


async def _resolve_market_projection_seed(symbol: str, timeframe: str) -> Optional[Dict[str, Any]]:
    try:
        from src.data.idx_fetcher import fetch_candlesticks

        payload = await fetch_candlesticks(symbol, timeframe=timeframe, limit=40)
        candles = (payload or {}).get("candles") or []
        if len(candles) < 6:
            return None

        closes = [
            _safe_float(candle.get("close"), default=None)
            for candle in candles
        ]
        closes = [float(value) for value in closes if value is not None and value > 0]
        if len(closes) < 6:
            return None

        current_price = closes[-1]
        returns = []
        for prev, curr in zip(closes[:-1], closes[1:]):
            if prev > 0:
                returns.append((curr / prev) - 1.0)

        if not returns:
            return None

        recent_window = closes[-5:]
        medium_window = closes[-20:] if len(closes) >= 20 else closes

        recent_avg = sum(recent_window) / len(recent_window)
        medium_avg = sum(medium_window) / len(medium_window)
        momentum_short = ((current_price / recent_avg) - 1.0) if recent_avg > 0 else 0.0
        momentum_long = ((current_price / medium_avg) - 1.0) if medium_avg > 0 else 0.0

        volatility = math.sqrt(sum(value * value for value in returns) / len(returns))
        trend_signal = (0.65 * momentum_short) + (0.35 * momentum_long)
        expected_return = max(-0.12, min(0.12, trend_signal * 1.8))

        confidence_base = 0.58 + min(0.24, abs(trend_signal) * 4.4)
        confidence_penalty = min(0.10, volatility * 2.0)
        confidence = max(0.52, min(0.90, confidence_base - confidence_penalty))

        signal = _signal_from_expected_return(
            expected_return,
            confidence,
            return_levels=[-0.06, 0.06],
        )

        return {
            "symbol": symbol,
            "signal": signal,
            "reason": "Realtime market momentum fallback generated from latest candle structure.",
            "confidence": confidence,
            "model_confidence": None,
            "expected_return": expected_return,
            "predicted_move": f"{expected_return * 100:+.2f}%",
            "current_price": current_price,
            "target_price": max(0.01, current_price * (1.0 + expected_return)),
            "source": "market_realtime",
            "architecture": None,
        }
    except Exception:
        return None


async def _emit_projection_notification(seed: Dict[str, Any], timeframe: str) -> None:
    try:
        from src.notifications.notification_service import (
            get_notification_manager,
            Notification,
            NotificationChannel,
            AlertSeverity,
            TradeSignalType,
        )

        manager = get_notification_manager()
        if not manager.websocket_connections:
            return

        symbol = str(seed.get("symbol") or "UNKNOWN")
        signal = str(seed.get("signal") or "HOLD")
        confidence = float(max(0.0, min(1.0, seed.get("confidence") or 0.0)))
        expected_return = float(seed.get("expected_return") or 0.0)

        signal_key = f"{signal}:{round(expected_return, 4)}:{round(confidence, 3)}"
        cache_key = (symbol, timeframe)
        if _projection_notification_state.get(cache_key) == signal_key:
            return

        _projection_notification_state[cache_key] = signal_key

        if signal in {"STRONG_BUY", "BUY"}:
            severity = AlertSeverity.INFO
            signal_type = TradeSignalType.BUY_SIGNAL
        elif signal in {"STRONG_SELL", "SELL"}:
            severity = AlertSeverity.WARNING
            signal_type = TradeSignalType.SELL_SIGNAL
        else:
            severity = AlertSeverity.INFO
            signal_type = TradeSignalType.TREND_CHANGE

        connected_users = list(manager.websocket_connections.keys())
        for user_id in connected_users:
            notification = Notification(
                rule_id=f"ai-projection-{symbol}",
                user_id=user_id,
                title=f"AI Projection {signal} · {symbol}",
                body=(
                    f"Realtime projection {timeframe}: move {expected_return * 100:+.2f}% "
                    f"with confidence {confidence * 100:.2f}%"
                ),
                data={
                    "symbol": symbol,
                    "signal": signal,
                    "timeframe": timeframe,
                    "expectedReturn": expected_return,
                    "confidence": confidence,
                    "source": seed.get("source"),
                },
                signal_type=signal_type,
                severity=severity,
                channels=[NotificationChannel.WEBSOCKET],
            )
            await manager.send_notification(notification, user_id=user_id)
    except Exception:
        return


async def _emit_regime_transition_notification(
    previous_regime: str,
    current_regime: str,
    regime_state: Dict[str, Any],
) -> None:
    try:
        from src.notifications.notification_service import (
            get_notification_manager,
            Notification,
            NotificationChannel,
            AlertSeverity,
            TradeSignalType,
        )

        manager = get_notification_manager()
        if not manager.websocket_connections:
            return

        transition_key = f"{previous_regime}->{current_regime}:{regime_state.get('asOf')}"
        if _regime_notification_state.get("major_transition") == transition_key:
            return
        _regime_notification_state["major_transition"] = transition_key

        severity = AlertSeverity.WARNING if current_regime == "BEAR" else AlertSeverity.INFO
        confidence = float(max(0.0, min(1.0, regime_state.get("confidence") or 0.0)))
        agent_name = str(regime_state.get("primaryAgent") or "scalper_agent")

        connected_users = list(manager.websocket_connections.keys())
        for user_id in connected_users:
            notification = Notification(
                rule_id=f"regime-transition-{previous_regime.lower()}-{current_regime.lower()}",
                user_id=user_id,
                title=f"Major Regime Shift {previous_regime} -> {current_regime}",
                body=(
                    f"Regime router pindah ke {current_regime} dengan confidence "
                    f"{confidence * 100:.1f}%. Active agent: {agent_name}."
                ),
                data={
                    "from": previous_regime,
                    "to": current_regime,
                    "confidence": confidence,
                    "primaryAgent": agent_name,
                    "riskMultiplier": regime_state.get("riskMultiplier"),
                },
                signal_type=TradeSignalType.TREND_CHANGE,
                severity=severity,
                channels=[NotificationChannel.WEBSOCKET],
            )
            await manager.send_notification(notification, user_id=user_id)
    except Exception:
        return


def _resolve_signal_universe(df: Any, preferred_universe: Optional[List[str]], max_symbols: int) -> List[str]:
    if "symbol" not in df.columns:
        return []

    available_symbols = [str(value) for value in df["symbol"].dropna().astype(str).tolist()]
    selected: List[str] = []

    for symbol in preferred_universe or []:
        normalized = str(symbol).strip()
        if not normalized:
            continue

        exact_match = next(
            (item for item in available_symbols if item == normalized),
            None,
        )
        if exact_match and exact_match not in selected:
            selected.append(exact_match)
            continue

        alias_match = next(
            (item for item in available_symbols if _symbols_match(item, normalized)),
            None,
        )
        if alias_match and alias_match not in selected:
            selected.append(alias_match)

    if not selected:
        if "t_index" in df.columns:
            latest = (
                df[["symbol", "t_index"]]
                .dropna(subset=["symbol"])
                .groupby("symbol", as_index=False)["t_index"]
                .max()
                .sort_values("t_index", ascending=False)
            )
            for value in latest["symbol"].tolist():
                symbol = str(value)
                if symbol not in selected:
                    selected.append(symbol)
        else:
            for symbol in available_symbols:
                if symbol not in selected:
                    selected.append(symbol)

    safe_max = max(1, int(max_symbols))
    return selected[:safe_max]


def _signal_from_expected_return(expected_return: float, confidence: float, return_levels: List[float]) -> str:
    if not return_levels:
        return_levels = [-0.01, 0.01]

    max_level = max(return_levels)
    min_level = min(return_levels)
    strong_buy_threshold = max(0.01, max_level * 0.7)
    strong_sell_threshold = min(-0.01, min_level * 0.7)

    if expected_return >= strong_buy_threshold and confidence >= 0.60:
        return "STRONG_BUY"
    if expected_return > 0.0 and confidence >= 0.52:
        return "BUY"
    if expected_return <= strong_sell_threshold and confidence >= 0.60:
        return "STRONG_SELL"
    if expected_return < 0.0 and confidence >= 0.52:
        return "SELL"
    return "HOLD"


def _risk_level_from_prediction(expected_return: float, confidence: float) -> str:
    absolute_move = abs(expected_return)
    if confidence >= 0.70 and absolute_move <= 0.02:
        return "Low"
    if confidence >= 0.60 and absolute_move <= 0.04:
        return "Low-Medium"
    if confidence >= 0.52 and absolute_move <= 0.07:
        return "Medium"
    return "High"


def _symbol_name(symbol: str) -> str:
    if symbol in _SYMBOL_NAME_MAP:
        return _SYMBOL_NAME_MAP[symbol]

    normalized = str(symbol or "").strip().upper()
    if normalized.endswith("=X") and len(normalized.replace("=X", "")) == 6:
        pair = normalized.replace("=X", "")
        return f"{pair[:3]}/{pair[3:]}"
    if "-" in normalized:
        return normalized.replace("-", "/")
    if normalized.endswith("USDT") and len(normalized) > 4:
        base = normalized[:-4]
        return f"{base}/USDT"

    return normalized


def _symbol_sector(symbol: str) -> str:
    return _SYMBOL_SECTOR_MAP.get(symbol, "Forex/Crypto")


def _load_transformer_runtime(project_root: Optional[str] = None) -> Optional[Dict[str, Any]]:
    root = project_root or _get_project_root()
    best_artifact = _resolve_best_transformer_artifact(root)
    if not best_artifact:
        return None

    model_path = best_artifact.get("path")
    model_mtime = best_artifact.get("mtime")
    if (
        _transformer_runtime_cache.get("runtime") is not None
        and _transformer_runtime_cache.get("path") == model_path
        and _transformer_runtime_cache.get("mtime") == model_mtime
    ):
        return _transformer_runtime_cache.get("runtime")

    try:
        import numpy as np
        import torch
        from src.ml.transformer_baselines import build_baseline_model

        checkpoint = torch.load(model_path, map_location="cpu")
        if not isinstance(checkpoint, dict):
            return None

        feature_columns = [str(col) for col in (checkpoint.get("feature_columns") or [])]
        if not feature_columns:
            return None

        architecture = str(
            checkpoint.get("architecture")
            or best_artifact.get("architecture")
            or "fusion"
        ).lower()
        train_config = checkpoint.get("train_config") or {}

        input_dim = int(checkpoint.get("input_dim") or len(feature_columns))
        raw_index_to_label = checkpoint.get("index_to_label") or {}
        num_classes = int(checkpoint.get("num_classes") or max(2, len(raw_index_to_label)))

        model = build_baseline_model(
            architecture=architecture,
            input_dim=input_dim,
            num_classes=num_classes,
            feature_columns=feature_columns,
            patch_sizes=train_config.get("patch_sizes") or [4, 8, 16],
            patch_stride=int(train_config.get("patch_stride", 4)),
            d_model=int(train_config.get("d_model", 128)),
            n_heads=int(train_config.get("n_heads", 4)),
            n_layers=int(train_config.get("n_layers", 2)),
            dropout=float(train_config.get("dropout", 0.1)),
        )

        state_dict = checkpoint.get("state_dict")
        if not state_dict:
            return None
        model.load_state_dict(state_dict)
        model.eval()

        mean_values = checkpoint.get("normalization_mean") or [0.0] * input_dim
        std_values = checkpoint.get("normalization_std") or [1.0] * input_dim
        mean = np.asarray(mean_values, dtype=np.float32).reshape(1, 1, -1)
        std = np.asarray(std_values, dtype=np.float32).reshape(1, 1, -1)
        std = np.where(np.abs(std) < 1e-6, 1.0, std).astype(np.float32)

        index_to_label: Dict[int, int] = {}
        for key, value in raw_index_to_label.items():
            try:
                idx = int(key)
                index_to_label[idx] = int(value)
            except Exception:
                continue

        runtime = {
            "model": model,
            "feature_columns": feature_columns,
            "normalization_mean": mean,
            "normalization_std": std,
            "index_to_label": index_to_label,
            "architecture": architecture,
            "source": best_artifact.get("source") or "transformer",
            "seq_len": int(train_config.get("seq_len", 32)),
        }

        _transformer_runtime_cache.update(
            {
                "path": model_path,
                "mtime": model_mtime,
                "runtime": runtime,
            }
        )
        return runtime
    except Exception:
        _transformer_runtime_cache.update({"path": model_path, "mtime": model_mtime, "runtime": None})
        return None


def _estimate_label_returns(df: Any) -> Dict[int, float]:
    if "label" not in df.columns or "future_return" not in df.columns:
        return {}

    stats = {}
    grouped = (
        df[["label", "future_return"]]
        .dropna(subset=["label", "future_return"])
        .groupby("label")["future_return"]
        .mean()
    )
    for label, value in grouped.items():
        try:
            stats[int(label)] = float(value)
        except Exception:
            continue
    return stats


def _build_symbol_sequences(
    df: Any,
    feature_columns: List[str],
    seq_len: int,
    symbols: List[str],
) -> List[Dict[str, Any]]:
    import numpy as np
    import pandas as pd

    if "symbol" not in df.columns or not feature_columns:
        return []

    work = df.copy()
    if "t_index" not in work.columns:
        work["t_index"] = np.arange(len(work), dtype=int)

    work["_row_order"] = np.arange(len(work), dtype=int)
    work = work.sort_values(["symbol", "t_index", "_row_order"], kind="mergesort").reset_index(drop=True)

    for col in feature_columns:
        if col not in work.columns:
            work[col] = 0.0

    for col in feature_columns:
        if pd.api.types.is_bool_dtype(work[col]):
            work[col] = work[col].astype(int)
        elif not pd.api.types.is_numeric_dtype(work[col]):
            work[col] = work[col].astype("category").cat.codes.astype(float)

    feature_frame = (
        work[feature_columns]
        .replace([np.inf, -np.inf], np.nan)
        .ffill()
        .bfill()
        .fillna(0.0)
        .astype(np.float32)
    )

    price_col = None
    for candidate in ["last_price", "close", "price", "adj_close", "open"]:
        if candidate in work.columns:
            price_col = candidate
            break

    samples: List[Dict[str, Any]] = []
    for symbol in symbols:
        symbol_mask = work["symbol"].astype(str) == str(symbol)
        if not bool(symbol_mask.any()):
            continue

        symbol_features = feature_frame.loc[symbol_mask].to_numpy(dtype=np.float32)
        if symbol_features.shape[0] < 1:
            continue

        if symbol_features.shape[0] >= seq_len:
            sequence = symbol_features[-seq_len:]
        else:
            pad = np.repeat(symbol_features[:1], repeats=(seq_len - symbol_features.shape[0]), axis=0)
            sequence = np.concatenate([pad, symbol_features], axis=0)

        symbol_rows = work.loc[symbol_mask]
        last_row = symbol_rows.iloc[-1]
        current_price = _safe_float(last_row.get(price_col), default=0.0) if price_col else 0.0

        samples.append(
            {
                "symbol": str(symbol),
                "sequence": sequence,
                "current_price": float(max(0.0, current_price)),
            }
        )

    return samples


def _extract_price_series_for_regime(
    df: Any,
    symbols: Optional[List[str]],
    max_points: int = 120,
) -> List[float]:
    if "symbol" not in df.columns:
        return []

    price_col = None
    for candidate in ["last_price", "close", "price", "adj_close", "open"]:
        if candidate in df.columns:
            price_col = candidate
            break

    if not price_col:
        return []

    candidate_symbols = [str(item) for item in (symbols or []) if str(item).strip()]
    if not candidate_symbols:
        candidate_symbols = [str(item) for item in df["symbol"].dropna().astype(str).unique()]

    for symbol in candidate_symbols:
        symbol_df = df[df["symbol"].astype(str) == symbol]
        if symbol_df.empty:
            continue

        price_values = (
            symbol_df[price_col]
            .replace([float("inf"), float("-inf")], float("nan"))
            .dropna()
            .astype(float)
            .tolist()
        )
        if len(price_values) >= 20:
            return [float(value) for value in price_values[-max_points:]]

    return []


def _normalize_strategy_profile_key(value: Any) -> Optional[str]:
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
    if resolved not in _PROFILE_ROUTE_PRESETS:
        return None
    return str(resolved)


def _resolve_manual_strategy_profile() -> Optional[str]:
    try:
        settings = _state_store.get_user_settings(_default_user_settings)
    except Exception:
        return None
    return _normalize_strategy_profile_key(settings.get("aiManualStrategyProfile"))


def _apply_strategy_profile_override_to_route(
    route: Any,
    manual_profile: Optional[str] = None,
) -> Tuple[Any, Optional[str]]:
    profile = _normalize_strategy_profile_key(manual_profile)
    if profile is None:
        profile = _resolve_manual_strategy_profile()

    if profile is None:
        return route, None

    preset = _PROFILE_ROUTE_PRESETS.get(profile) or {}
    return (
        SimpleNamespace(
            regime=str(getattr(route, "regime", "UNKNOWN")),
            confidence=float(max(0.0, min(1.0, getattr(route, "confidence", 0.0)))),
            primary_agent=str(preset.get("primaryAgent") or getattr(route, "primary_agent", "scalper_agent")),
            strategy_profile=str(profile),
            risk_multiplier=float(preset.get("riskMultiplier", getattr(route, "risk_multiplier", 0.75))),
            trend_return=float(getattr(route, "trend_return", 0.0)),
            volatility=float(max(0.0, getattr(route, "volatility", 0.0))),
            up_move_ratio=float(max(0.0, min(1.0, getattr(route, "up_move_ratio", 0.5)))),
        ),
        profile,
    )


def _sync_regime_profile_override(manual_profile_value: Any) -> Dict[str, Any]:
    active_profile = _normalize_strategy_profile_key(manual_profile_value)
    current_regime = _state_store.get_regime_state(_default_regime_state)

    if active_profile is None:
        return _state_store.set_regime_state(
            {
                **current_regime,
                "manualProfileOverride": False,
                "profileSource": "regime_router",
                "asOf": datetime.now().isoformat(),
            }
        )

    profile_preset = _PROFILE_ROUTE_PRESETS.get(active_profile) or {}
    return _state_store.set_regime_state(
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


def _build_regime_state_payload(
    route: Any,
    symbols: Optional[List[str]],
    price_points: int,
    manual_profile_override: Optional[str] = None,
) -> Dict[str, Any]:
    active_manual_profile = _normalize_strategy_profile_key(manual_profile_override)
    active_profile = str(getattr(route, "strategy_profile", "mean_reversion_swing"))
    if active_manual_profile is not None:
        active_profile = active_manual_profile

    profile_preset = _PROFILE_ROUTE_PRESETS.get(active_profile) or {}
    primary_agent = str(profile_preset.get("primaryAgent") or getattr(route, "primary_agent", "scalper_agent"))
    risk_multiplier = float(profile_preset.get("riskMultiplier", getattr(route, "risk_multiplier", 0.75)))

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


def _persist_regime_route(
    route: Any,
    symbols: Optional[List[str]],
    price_points: int,
    manual_profile_override: Optional[str] = None,
) -> None:
    try:
        previous_state = _state_store.get_regime_state(_default_regime_state)
        next_state = _build_regime_state_payload(
            route,
            symbols,
            price_points,
            manual_profile_override=manual_profile_override,
        )
        saved_state = _state_store.set_regime_state(next_state)

        previous_regime = str(previous_state.get("regime") or "UNKNOWN").upper()
        current_regime = str(saved_state.get("regime") or "UNKNOWN").upper()
        if (
            previous_regime not in {"", "UNKNOWN"}
            and current_regime not in {"", "UNKNOWN"}
            and previous_regime != current_regime
        ):
            is_major_transition = {previous_regime, current_regime} == {"BULL", "BEAR"}
            _state_store.append_ai_log(
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
                        _emit_regime_transition_notification(
                            previous_regime,
                            current_regime,
                            saved_state,
                        )
                    )
                except Exception:
                    pass
    except Exception:
        pass


def _resolve_regime_route(df: Any, symbols: Optional[List[str]]) -> Optional[Any]:
    try:
        from src.ml.regime_router import classify_market_regime

        price_series = _extract_price_series_for_regime(df, symbols)
        if not price_series:
            return None
        route = classify_market_regime(price_series)
        route, active_manual_profile = _apply_strategy_profile_override_to_route(route)
        _persist_regime_route(
            route,
            symbols=symbols,
            price_points=len(price_series),
            manual_profile_override=active_manual_profile,
        )
        return route
    except Exception:
        return None


def _infer_signals_from_transformer(limit: int, preferred_universe: Optional[List[str]]) -> List[Signal]:
    import numpy as np

    safe_limit = max(1, int(limit))
    dataset_csv = _resolve_dataset_csv_path()
    if not os.path.exists(dataset_csv):
        return []

    runtime = _load_transformer_runtime()
    if runtime is None:
        return []

    try:
        import pandas as pd
        import torch

        df = pd.read_csv(dataset_csv)
        if df.empty or "symbol" not in df.columns:
            return []

        symbols = _resolve_signal_universe(df, preferred_universe, max_symbols=max(safe_limit * 3, 6))
        if not symbols:
            return []

        regime_route = _resolve_regime_route(df, symbols)
        regime_overlay_fn = None
        if regime_route is not None:
            try:
                from src.ml.regime_router import apply_regime_overlay

                regime_overlay_fn = apply_regime_overlay
            except Exception:
                regime_overlay_fn = None

        samples = _build_symbol_sequences(
            df,
            feature_columns=runtime["feature_columns"],
            seq_len=int(runtime["seq_len"]),
            symbols=symbols,
        )
        if not samples:
            return []

        x = np.stack([item["sequence"] for item in samples], axis=0).astype(np.float32)
        mean = runtime["normalization_mean"]
        std = runtime["normalization_std"]
        if mean.shape[-1] != x.shape[-1] or std.shape[-1] != x.shape[-1]:
            mean = np.zeros((1, 1, x.shape[-1]), dtype=np.float32)
            std = np.ones((1, 1, x.shape[-1]), dtype=np.float32)

        normalized = ((x - mean) / std).astype(np.float32)
        tensor = torch.tensor(normalized, dtype=torch.float32)

        with torch.no_grad():
            logits = runtime["model"](tensor)
            probs = torch.softmax(logits, dim=1).cpu().numpy()

        label_returns = _estimate_label_returns(df)
        return_levels = list(label_returns.values())
        generated_at = datetime.now().isoformat()
        ranked_rows: List[Dict[str, Any]] = []

        for index, sample in enumerate(samples):
            probabilities = probs[index]
            pred_idx = int(np.argmax(probabilities))
            confidence = float(np.max(probabilities))

            predicted_label = runtime["index_to_label"].get(pred_idx, pred_idx)
            try:
                predicted_label_int = int(predicted_label)
            except Exception:
                predicted_label_int = pred_idx

            expected_return = float(label_returns.get(predicted_label_int, 0.0))
            signal_name = _signal_from_expected_return(expected_return, confidence, return_levels)

            regime_note = ""
            if regime_overlay_fn is not None and regime_route is not None:
                signal_name, expected_return, regime_note = regime_overlay_fn(
                    signal=signal_name,
                    expected_return=expected_return,
                    model_confidence=confidence,
                    route=regime_route,
                )

            current_price = float(sample["current_price"])
            target_price = current_price * (1.0 + expected_return) if current_price > 0 else 0.0

            base_reason = (
                f"{str(runtime['architecture']).upper()} model ({runtime['source']}) "
                f"predicted class {predicted_label_int} with {confidence * 100:.1f}% confidence."
            )
            if regime_note:
                base_reason = f"{base_reason} {regime_note}"

            ranked_rows.append(
                {
                    "rank": confidence * (abs(expected_return) + 0.001),
                    "symbol": sample["symbol"],
                    "name": _symbol_name(sample["symbol"]),
                    "signal": signal_name,
                    "confidence": confidence,
                    "reason": base_reason,
                    "predictedMove": f"{expected_return * 100:+.2f}%",
                    "riskLevel": _risk_level_from_prediction(expected_return, confidence),
                    "sector": _symbol_sector(sample["symbol"]),
                    "currentPrice": current_price,
                    "targetPrice": float(max(0.0, target_price)),
                    "timestamp": generated_at,
                }
            )

        ranked_rows.sort(key=lambda item: item["rank"], reverse=True)

        signals: List[Signal] = []
        for rank, row in enumerate(ranked_rows[:safe_limit], start=1):
            signals.append(
                Signal(
                    id=rank,
                    symbol=row["symbol"],
                    name=row["name"],
                    signal=row["signal"],
                    confidence=row["confidence"],
                    reason=row["reason"],
                    predictedMove=row["predictedMove"],
                    riskLevel=row["riskLevel"],
                    sector=row["sector"],
                    currentPrice=row["currentPrice"],
                    targetPrice=row["targetPrice"],
                    timestamp=row["timestamp"],
                )
            )

        return signals
    except Exception:
        return []


def _build_fallback_signals(limit: int, preferred_universe: Optional[List[str]]) -> List[Signal]:
    safe_limit = max(1, int(limit))
    dataset_csv = _resolve_dataset_csv_path()

    try:
        import pandas as pd

        if os.path.exists(dataset_csv):
            df = pd.read_csv(dataset_csv)
            if (not df.empty) and ("symbol" in df.columns):
                symbols = _resolve_signal_universe(df, preferred_universe, max_symbols=max(safe_limit * 3, 6))
                generated_at = datetime.now().isoformat()
                rows: List[Dict[str, Any]] = []

                regime_route = _resolve_regime_route(df, symbols)
                regime_overlay_fn = None
                if regime_route is not None:
                    try:
                        from src.ml.regime_router import apply_regime_overlay

                        regime_overlay_fn = apply_regime_overlay
                    except Exception:
                        regime_overlay_fn = None

                for symbol in symbols:
                    symbol_df = df[df["symbol"].astype(str) == str(symbol)]
                    if symbol_df.empty:
                        continue
                    last_row = symbol_df.iloc[-1]

                    momentum = _safe_float(last_row.get("momentum"), default=0.0)
                    short_sma = _safe_float(last_row.get("short_sma"), default=0.0)
                    long_sma = _safe_float(last_row.get("long_sma"), default=0.0)
                    current_price = _safe_float(last_row.get("last_price"), default=0.0)

                    trend_gap = ((short_sma - long_sma) / long_sma) if long_sma > 0 else 0.0
                    expected_return = max(-0.08, min(0.08, (0.6 * momentum) + (0.4 * trend_gap)))
                    confidence = max(0.50, min(0.85, 0.55 + (abs(expected_return) * 4.0)))
                    signal_name = _signal_from_expected_return(
                        expected_return,
                        confidence,
                        return_levels=[-abs(expected_return), abs(expected_return)],
                    )

                    regime_note = ""
                    if regime_overlay_fn is not None and regime_route is not None:
                        signal_name, expected_return, regime_note = regime_overlay_fn(
                            signal=signal_name,
                            expected_return=expected_return,
                            model_confidence=confidence,
                            route=regime_route,
                        )

                    base_reason = (
                        "Fallback technical heuristic using momentum and SMA trend gap "
                        "while transformer signal model is unavailable."
                    )
                    if regime_note:
                        base_reason = f"{base_reason} {regime_note}"

                    rows.append(
                        {
                            "rank": confidence * (abs(expected_return) + 0.001),
                            "symbol": str(symbol),
                            "name": _symbol_name(str(symbol)),
                            "signal": signal_name,
                            "confidence": confidence,
                            "reason": base_reason,
                            "predictedMove": f"{expected_return * 100:+.2f}%",
                            "riskLevel": _risk_level_from_prediction(expected_return, confidence),
                            "sector": _symbol_sector(str(symbol)),
                            "currentPrice": float(max(0.0, current_price)),
                            "targetPrice": float(max(0.0, current_price * (1.0 + expected_return))),
                            "timestamp": generated_at,
                        }
                    )

                rows.sort(key=lambda item: item["rank"], reverse=True)
                if rows:
                    return [
                        Signal(
                            id=index,
                            symbol=item["symbol"],
                            name=item["name"],
                            signal=item["signal"],
                            confidence=item["confidence"],
                            reason=item["reason"],
                            predictedMove=item["predictedMove"],
                            riskLevel=item["riskLevel"],
                            sector=item["sector"],
                            currentPrice=item["currentPrice"],
                            targetPrice=item["targetPrice"],
                            timestamp=item["timestamp"],
                        )
                        for index, item in enumerate(rows[:safe_limit], start=1)
                    ]
    except Exception:
        pass

    # Absolute fallback to maintain API contract.
    return [
        Signal(
            id=1,
            symbol="EURUSD=X",
            name="EUR/USD",
            signal="HOLD",
            confidence=0.5,
            reason="No valid model output is available yet; fallback signal is neutral.",
            predictedMove="+0.00%",
            riskLevel="Medium",
            sector="Forex",
            currentPrice=1.0,
            targetPrice=1.0,
            timestamp=datetime.now().isoformat(),
        )
    ][:safe_limit]


def _parse_predicted_move(predicted_move: Any) -> Optional[float]:
    raw = str(predicted_move or "").strip().replace("%", "")
    if not raw:
        return None
    parsed = _safe_float(raw, default=None)
    if parsed is None:
        return None
    return float(parsed) / 100.0


def _signal_to_projection_seed(signal: Signal, source: str) -> Dict[str, Any]:
    current_price = _safe_float(signal.currentPrice, default=0.0) or 0.0
    target_price = _safe_float(signal.targetPrice, default=current_price) or current_price

    expected_return = 0.0
    if current_price > 0:
        expected_return = (target_price / current_price) - 1.0
    elif current_price <= 0:
        parsed_move = _parse_predicted_move(signal.predictedMove)
        if parsed_move is not None:
            expected_return = parsed_move

    return {
        "symbol": _normalize_symbol_input(signal.symbol),
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


def _predict_projection_seed(symbol: str, market: Optional[str] = None) -> Dict[str, Any]:
    normalized_symbol = _normalize_symbol_input(symbol, market=market)

    transformer_signals = _infer_signals_from_transformer(
        limit=8,
        preferred_universe=[normalized_symbol],
    )
    for item in transformer_signals:
        if _symbols_match(item.symbol, normalized_symbol):
            runtime = _load_transformer_runtime()
            architecture = runtime.get("architecture") if runtime else None
            payload = _signal_to_projection_seed(item, source="transformer")
            payload["architecture"] = architecture
            return payload

    fallback_signals = _build_fallback_signals(
        limit=8,
        preferred_universe=[normalized_symbol],
    )
    for item in fallback_signals:
        if _symbols_match(item.symbol, normalized_symbol):
            payload = _signal_to_projection_seed(item, source="fallback")
            payload["architecture"] = None
            return payload

    return {
        "symbol": normalized_symbol,
        "signal": "HOLD",
        "reason": "No model signal available; projection defaults to neutral.",
        "confidence": 0.5,
        "model_confidence": None,
        "expected_return": 0.0,
        "predicted_move": "+0.00%",
        "current_price": 0.0,
        "target_price": 0.0,
        "source": "fallback",
        "architecture": None,
    }


def _resolve_timeframe_seconds(timeframe: str) -> int:
    normalized = str(timeframe or "").strip().lower()
    return _TIMEFRAME_SECONDS.get(normalized, _TIMEFRAME_SECONDS["1d"])


def _build_projection_points(
    base_time: int,
    current_price: float,
    expected_return: float,
    timeframe: str,
    horizon: int,
) -> List[AIProjectionPoint]:
    safe_horizon = max(1, int(horizon))
    safe_price = float(max(0.01, current_price))
    interval_seconds = _resolve_timeframe_seconds(timeframe)

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


async def _resolve_latest_candle_anchor(symbol: str, timeframe: str) -> Optional[Dict[str, float]]:
    try:
        from src.data.idx_fetcher import fetch_candlesticks

        payload = await fetch_candlesticks(symbol, timeframe=timeframe, limit=1)
        candles = (payload or {}).get("candles") or []
        if not candles:
            return None

        last_candle = candles[-1]
        raw_time = int(last_candle.get("time") or 0)
        raw_close = _safe_float(last_candle.get("close"), default=None)
        if raw_time <= 0 or raw_close is None or raw_close <= 0:
            return None

        return {
            "time": float(raw_time),
            "price": float(raw_close),
        }
    except Exception:
        return None

def _parse_iso_datetime(value: Optional[str]) -> Optional[datetime]:
    raw_value = str(value or "").strip()
    if not raw_value:
        return None

    candidate = raw_value
    if candidate.endswith("Z"):
        candidate = candidate[:-1] + "+00:00"

    try:
        return datetime.fromisoformat(candidate)
    except Exception:
        return None


def _format_runtime_uptime(total_seconds: int) -> str:
    safe_seconds = max(0, int(total_seconds))
    hours = safe_seconds // 3600
    minutes = (safe_seconds % 3600) // 60
    if hours > 0:
        return f"{hours}h {minutes}m"
    return f"{minutes}m"


async def _run_blocking(func: Any, *args: Any, **kwargs: Any) -> Any:
    """Run blocking work in a thread to keep async routes responsive."""
    call = partial(func, *args, **kwargs)
    try:
        return await asyncio.to_thread(call)
    except AttributeError:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, call)


async def _resolve_runtime_portfolio_snapshot() -> Portfolio:
    starting_cash = float(
        _safe_float(os.getenv("PAPER_STARTING_CASH"), default=100_000_000.0)
        or 100_000_000.0
    )

    adapter = PaperBrokerAdapter(starting_cash=starting_cash)
    positions_map: Dict[str, Any] = {}
    cash = starting_cash
    balance = starting_cash

    try:
        adapter.connect()
        snapshot = adapter.reconcile() or {}
        positions_map = snapshot.get("positions") or {}
        cash = float(_safe_float(snapshot.get("cash"), default=starting_cash) or starting_cash)
        balance = float(_safe_float(snapshot.get("balance"), default=cash) or cash)
    except Exception:
        positions_map = {}
        cash = starting_cash
        balance = starting_cash
    finally:
        try:
            adapter.disconnect()
        except Exception:
            pass

    positions: List[PortfolioPosition] = []
    market_value = 0.0

    for raw_symbol, raw_quantity in positions_map.items():
        market_hint = _detect_market_from_symbol(str(raw_symbol))
        symbol = _normalize_symbol_input(str(raw_symbol), market=market_hint)
        quantity = int(_safe_float(raw_quantity, default=0.0) or 0.0)
        if quantity <= 0:
            continue

        anchor = await _resolve_latest_candle_anchor(symbol, timeframe="1d")
        current_price = float((anchor or {}).get("price") or 0.0)
        entry_price = current_price
        total_value = float(quantity * current_price)
        market_value += total_value

        positions.append(
            PortfolioPosition(
                symbol=symbol,
                name=_symbol_name(symbol),
                quantity=quantity,
                entryPrice=entry_price,
                currentPrice=current_price,
                totalValue=total_value,
                p_l=0.0,
                percentP_L=0.0,
                sector=_symbol_sector(symbol),
                riskScore="Moderate",
            )
        )

    total_value = float(_safe_float(balance, default=(cash + market_value)) or (cash + market_value))
    total_p_l = float(total_value - starting_cash)
    percent_p_l = float((total_p_l / starting_cash) * 100.0) if starting_cash > 0 else 0.0

    return Portfolio(
        totalValue=round(total_value, 2),
        totalP_L=round(total_p_l, 2),
        percentP_L=round(percent_p_l, 4),
        cash=round(cash, 2),
        purchasingPower=round(cash, 2),
        lastUpdate=datetime.now().isoformat(),
        positions=positions,
    )


def _resolve_runtime_bot_status() -> BotStatus:
    logs = _state_store.list_ai_logs(limit=250)
    settings = _state_store.get_user_settings(_default_user_settings)
    broker = _state_store.get_broker_connection(_default_broker_connection)
    system_control = _state_store.get_system_control(_default_system_control)
    kill_switch_active = bool(system_control.get("killSwitchActive"))
    kill_switch_reason = str(system_control.get("reason") or "").strip() or None

    trade_like_events = {
        "trade_execution",
        "trade_reconcile",
        "strategy_deploy",
        "strategy_backtest",
    }

    now = datetime.now()
    parsed_timestamps = [
        _parse_iso_datetime(item.get("timestamp"))
        for item in logs
    ]
    parsed_timestamps = [item for item in parsed_timestamps if item is not None]

    earliest = min(parsed_timestamps) if parsed_timestamps else None
    uptime = _format_runtime_uptime(int((now - earliest).total_seconds())) if earliest else None

    today = now.date()
    total_trades_today = 0
    successful_trades = 0
    failed_trades = 0
    last_trade_time = None

    for item in logs:
        event_type = str(item.get("eventType") or "").strip().lower()
        level = str(item.get("level") or "").strip().lower()
        timestamp = _parse_iso_datetime(item.get("timestamp"))

        is_trade_like = event_type in trade_like_events or event_type.startswith("trade")
        if not is_trade_like:
            continue

        if timestamp and timestamp.date() == today:
            total_trades_today += 1
            if level == "error":
                failed_trades += 1
            elif level in {"info", "success"}:
                successful_trades += 1

        if timestamp and (last_trade_time is None or timestamp > last_trade_time):
            last_trade_time = timestamp

    resolved_total = successful_trades + failed_trades
    win_rate = float(successful_trades / resolved_total) if resolved_total > 0 else 0.0

    refresh_seconds = int(
        _safe_float(settings.get("aiMonitorRefreshSeconds"), default=20.0) or 20.0
    )
    refresh_seconds = max(5, min(refresh_seconds, 300))

    if kill_switch_active:
        resolved_status = "stopped"
        next_analysis = "halted"
    else:
        resolved_status = "running" if bool(broker.get("connected")) else "standby"
        next_analysis = f"{refresh_seconds}s"

    return BotStatus(
        status=resolved_status,
        uptime=uptime,
        activeTrades=0,
        totalTradesToday=total_trades_today,
        successfulTrades=successful_trades,
        failedTrades=failed_trades,
        winRate=round(win_rate, 4),
        lastTradeTime=last_trade_time.isoformat() if last_trade_time else None,
        nextAnalysisIn=next_analysis,
        killSwitchActive=kill_switch_active,
        killSwitchReason=kill_switch_reason,
        performanceToday={"totalP_L": 0.0, "percentP_L": 0.0},
    )


def _kill_switch_state() -> Dict[str, Any]:
    return _state_store.get_system_control(_default_system_control)


def _extract_auth_token_from_request(request: Optional[Request]) -> str:
    if request is None or not hasattr(request, "cookies"):
        return ""
    return str(request.cookies.get("auth_token") or "").strip()


def _session_context_from_request(request: Optional[Request]) -> Optional[Dict[str, Any]]:
    token = _extract_auth_token_from_request(request)
    if not token:
        return None

    context = get_session_context(token)
    if context:
        return context

    # Backward compatibility for sessions created before context fields existed.
    username = get_user_from_token(token)
    if not username:
        return None

    return {
        "username": username,
        "role": "",
        "csrfToken": "",
    }


def _assert_csrf_guard(
    request: Optional[Request],
    operation: str,
    *,
    require_authenticated: bool = False,
) -> Optional[Dict[str, Any]]:
    session_context = _session_context_from_request(request)

    if require_authenticated and not session_context:
        raise HTTPException(
            status_code=401,
            detail=f"{operation} requires authenticated session.",
        )

    if not session_context:
        return None

    require_csrf_default = str(os.getenv("ENV", "")).strip().lower() in {
        "prod",
        "production",
    }
    require_csrf = _env_flag(
        "AUTOSAHAM_CSRF_PROTECTION_ENABLED",
        require_csrf_default,
    )
    if not require_csrf:
        return session_context

    header_token = ""
    cookie_token = ""
    if request is not None and hasattr(request, "headers"):
        header_token = str(
            request.headers.get("x-csrf-token")
            or request.headers.get("x-xsrf-token")
            or ""
        ).strip()
    if request is not None and hasattr(request, "cookies"):
        cookie_token = str(request.cookies.get("csrf_token") or "").strip()

    session_csrf = str(session_context.get("csrfToken") or "").strip()

    if not header_token or not cookie_token:
        raise HTTPException(
            status_code=403,
            detail=f"{operation} blocked: missing CSRF token.",
        )

    if not hmac.compare_digest(header_token, cookie_token):
        raise HTTPException(
            status_code=403,
            detail=f"{operation} blocked: CSRF token mismatch.",
        )

    if session_csrf and not hmac.compare_digest(header_token, session_csrf):
        raise HTTPException(
            status_code=403,
            detail=f"{operation} blocked: invalid CSRF token.",
        )

    return session_context


def _env_flag(name: str, default: bool = False) -> bool:
    raw = str(os.getenv(name, "")).strip().lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "on"}


def _parse_csv_set(value: str) -> set[str]:
    return {
        item.strip().lower()
        for item in str(value or "").split(",")
        if item.strip()
    }


def _is_admin_session(session_context: Optional[Dict[str, Any]]) -> bool:
    if not session_context:
        return False

    session_user = str(session_context.get("username") or "").strip().lower()
    session_role = str(session_context.get("role") or "").strip().lower()

    admin_users = _parse_csv_set(os.getenv("AUTOSAHAM_ADMIN_USERS", ""))
    if not admin_users:
        admin_users = _parse_csv_set(
            os.getenv("AUTOSAHAM_KILL_SWITCH_ADMIN_USERS", "admin")
        )
    if not admin_users:
        admin_users = {"admin"}

    admin_roles = _parse_csv_set(
        os.getenv("AUTOSAHAM_ADMIN_ROLES", "admin")
    )
    if not admin_roles:
        admin_roles = {"admin"}

    return (session_user in admin_users) or (session_role in admin_roles)


def _require_admin_operation(request: Optional[Request], operation: str) -> Dict[str, Any]:
    require_admin_default = str(os.getenv("ENV", "")).strip().lower() in {
        "prod",
        "production",
    }
    require_admin = _env_flag("AUTOSAHAM_ADMIN_GUARD_ENABLED", require_admin_default)

    session_context = _assert_csrf_guard(
        request,
        operation,
        require_authenticated=require_admin,
    )

    if not require_admin:
        return session_context or {
            "username": "api",
            "role": "system",
            "csrfToken": "",
        }

    if not session_context:
        raise HTTPException(
            status_code=401,
            detail=f"{operation} requires authenticated admin session.",
        )

    if not _is_admin_session(session_context):
        raise HTTPException(
            status_code=403,
            detail=f"{operation} requires admin role.",
        )

    return session_context


def _require_role_operation(
    request: Optional[Request],
    operation: str,
    *,
    allowed_roles: set[str],
    allow_admin_override: bool = True,
) -> Dict[str, Any]:
    require_role_default = str(os.getenv("ENV", "")).strip().lower() in {
        "prod",
        "production",
    }
    require_role_guard = _env_flag(
        "AUTOSAHAM_ROLE_GUARD_ENABLED",
        require_role_default,
    )

    session_context = _assert_csrf_guard(
        request,
        operation,
        require_authenticated=require_role_guard,
    )

    if not require_role_guard:
        return session_context or {
            "username": "api",
            "role": "system",
            "csrfToken": "",
        }

    if not session_context:
        raise HTTPException(
            status_code=401,
            detail=f"{operation} requires authenticated session.",
        )

    if allow_admin_override and _is_admin_session(session_context):
        return session_context

    normalized_allowed = {str(role).strip().lower() for role in allowed_roles if str(role).strip()}
    session_role = str(session_context.get("role") or "").strip().lower()
    if session_role not in normalized_allowed:
        raise HTTPException(
            status_code=403,
            detail=f"{operation} requires one of roles: {', '.join(sorted(normalized_allowed))}",
        )

    return session_context


def _totp_code_at(
    secret: str,
    timestamp: int,
    *,
    step_seconds: int = 30,
    digits: int = 6,
) -> Optional[str]:
    normalized_secret = "".join(str(secret or "").strip().split()).upper()
    if not normalized_secret:
        return None

    try:
        secret_bytes = base64.b32decode(normalized_secret, casefold=True)
    except (binascii.Error, ValueError, TypeError):
        return None

    step = max(1, int(step_seconds))
    counter = int(timestamp // step)
    msg = counter.to_bytes(8, "big")
    digest = hmac.new(secret_bytes, msg, hashlib.sha1).digest()
    offset = digest[-1] & 0x0F

    binary_code = (
        ((digest[offset] & 0x7F) << 24)
        | (digest[offset + 1] << 16)
        | (digest[offset + 2] << 8)
        | digest[offset + 3]
    )

    modulus = 10 ** max(1, int(digits))
    return str(binary_code % modulus).zfill(max(1, int(digits)))


def _verify_totp_code(
    secret: str,
    code: str,
    *,
    step_seconds: int = 30,
    window: int = 1,
) -> bool:
    normalized_code = str(code or "").strip()
    if not normalized_code or not normalized_code.isdigit():
        return False

    now_ts = int(datetime.now().timestamp())
    valid_window = max(0, int(window))
    for drift in range(-valid_window, valid_window + 1):
        current_ts = now_ts + drift * int(step_seconds)
        expected = _totp_code_at(
            secret,
            current_ts,
            step_seconds=step_seconds,
            digits=len(normalized_code),
        )
        if expected and hmac.compare_digest(expected, normalized_code):
            return True

    return False


def _authorize_kill_switch_actor(
    request: Optional[Request],
    payload: Optional[KillSwitchPayload],
) -> str:
    payload_actor = str(
        (
            payload.actor
            if payload and payload.actor is not None
            else (payload.activatedBy if payload else "")
        )
        or ""
    ).strip()

    session_context = _assert_csrf_guard(request, "Kill switch", require_authenticated=False)
    session_user = str((session_context or {}).get("username") or "").strip() or None
    session_role = str((session_context or {}).get("role") or "").strip().lower() or None

    require_admin_default = str(os.getenv("ENV", "")).strip().lower() in {
        "prod",
        "production",
    }
    require_admin = _env_flag(
        "AUTOSAHAM_KILL_SWITCH_REQUIRE_ADMIN",
        require_admin_default,
    )

    admin_users = _parse_csv_set(os.getenv("AUTOSAHAM_KILL_SWITCH_ADMIN_USERS", "admin"))
    if not admin_users:
        admin_users = {"admin"}
    admin_roles = _parse_csv_set(
        os.getenv("AUTOSAHAM_KILL_SWITCH_ADMIN_ROLES", os.getenv("AUTOSAHAM_ADMIN_ROLES", "admin"))
    )
    if not admin_roles:
        admin_roles = {"admin"}

    if require_admin:
        if not session_user:
            raise HTTPException(
                status_code=401,
                detail="Kill switch requires authenticated admin session.",
            )
        if (
            str(session_user).strip().lower() not in admin_users
            and str(session_role or "").strip().lower() not in admin_roles
        ):
            raise HTTPException(
                status_code=403,
                detail="Kill switch requires admin role.",
            )

    challenge_code = str((payload.challengeCode if payload else "") or "").strip()
    totp_secret = str(os.getenv("AUTOSAHAM_KILL_SWITCH_TOTP_SECRET", "")).strip()
    fallback_code = str(os.getenv("AUTOSAHAM_KILL_SWITCH_2FA_CODE", "")).strip()
    require_2fa = _env_flag(
        "AUTOSAHAM_KILL_SWITCH_REQUIRE_2FA",
        bool(totp_secret or fallback_code),
    )

    if require_2fa:
        if not challenge_code:
            raise HTTPException(
                status_code=401,
                detail="Kill switch requires 2FA challenge code.",
            )

        if totp_secret:
            if not _verify_totp_code(totp_secret, challenge_code):
                raise HTTPException(
                    status_code=401,
                    detail="Invalid 2FA challenge code.",
                )
        elif fallback_code:
            if not hmac.compare_digest(fallback_code, challenge_code):
                raise HTTPException(
                    status_code=401,
                    detail="Invalid 2FA challenge code.",
                )
        else:
            raise HTTPException(
                status_code=503,
                detail="Kill switch 2FA enabled but verifier is not configured.",
            )

    resolved_actor = payload_actor or str(session_user or "").strip() or "api"
    return resolved_actor


def _is_kill_switch_active() -> bool:
    state = _kill_switch_state()
    return bool(state.get("killSwitchActive"))


def _assert_kill_switch_inactive(operation: str) -> None:
    state = _kill_switch_state()
    if not bool(state.get("killSwitchActive")):
        return

    reason = str(state.get("reason") or "Emergency stop active")
    raise HTTPException(
        status_code=423,
        detail=f"{operation} blocked: {reason}",
    )


def _emit_kill_switch_event(active: bool, reason: str, actor: str) -> None:
    try:
        from src.api.event_queue import push_event

        push_event(
            {
                "type": "kill_switch",
                "active": bool(active),
                "reason": reason,
                "actor": actor,
                "timestamp": datetime.now().isoformat(),
            }
        )
    except Exception:
        pass


def _runtime_scheduler_status() -> Dict[str, Any]:
    status: Dict[str, Any] = {
        "available": False,
        "running": False,
    }
    try:
        from src.api import server as api_server

        scheduler = getattr(api_server, "_scheduler", None)
        if scheduler is None:
            return status

        thread = getattr(scheduler, "_thread", None)
        status.update(
            {
                "available": True,
                "running": bool(thread and thread.is_alive()),
            }
        )
    except Exception as exc:
        status["error"] = str(exc)

    return status


def _runtime_execution_status() -> Dict[str, Any]:
    status: Dict[str, Any] = {
        "available": False,
        "pendingOrders": 0,
        "startupSync": {
            "required": False,
            "completed": True,
            "status": "not_required",
        },
    }
    try:
        from src.api import server as api_server

        execution_manager = getattr(api_server, "_execution_manager", None)
        if execution_manager is None:
            return status

        pending_orders = []
        if hasattr(execution_manager, "get_pending_orders"):
            pending_orders = list(execution_manager.get_pending_orders() or [])

        startup_sync_status = status.get("startupSync")
        if hasattr(execution_manager, "get_startup_sync_status"):
            candidate = execution_manager.get_startup_sync_status()
            if isinstance(candidate, dict):
                startup_sync_status = {
                    **(startup_sync_status or {}),
                    **candidate,
                }

        status.update(
            {
                "available": True,
                "pendingOrders": len(pending_orders),
                "startupSync": startup_sync_status,
            }
        )
    except Exception as exc:
        status["error"] = str(exc)

    return status


def _runtime_execution_manager() -> Optional[Any]:
    try:
        from src.api import server as api_server

        return getattr(api_server, "_execution_manager", None)
    except Exception:
        return None


def _resolve_live_broker_adapter(provider: str):
    normalized = str(provider or "").strip().lower()

    if normalized == "indopremier":
        from src.brokers.indopremier import IndoPremierBroker

        return IndoPremierBroker
    if normalized == "stockbit":
        from src.brokers.stockbit import StockbitBroker

        return StockbitBroker
    if normalized == "ajaib":
        from src.brokers.ajaib import AjaibBroker

        return AjaibBroker

    return None


def _cancel_live_broker_open_orders(limit: int = 200) -> Dict[str, Any]:
    """Best-effort cancel for open orders on live broker connection."""
    safe_limit = max(1, min(1000, int(limit)))
    summary: Dict[str, Any] = {
        "requested": False,
        "connected": False,
        "provider": None,
        "status": "skipped",
        "openOrders": 0,
        "cancelled": 0,
        "failed": 0,
        "error": None,
    }

    connection = _state_store.get_broker_connection(_default_broker_connection)
    if not bool(connection.get("connected")):
        summary["status"] = "skipped_not_connected"
        return summary

    trading_mode = str(connection.get("tradingMode") or "paper").strip().lower()
    if trading_mode != "live":
        summary["status"] = "skipped_not_live"
        return summary

    provider = str(connection.get("provider") or "").strip().lower()
    summary["provider"] = provider or None

    adapter_cls = _resolve_live_broker_adapter(provider)
    if adapter_cls is None:
        summary["status"] = "unsupported_provider"
        return summary

    credentials = _state_store.get_broker_credentials()
    account_id = str(
        connection.get("accountId")
        or credentials.get("accountId")
        or ""
    ).strip()
    api_key = str(credentials.get("apiKey") or "").strip()
    api_secret = str(credentials.get("apiSecret") or "").strip()

    if not account_id or not api_key or not api_secret:
        summary["status"] = "missing_credentials"
        return summary

    summary["requested"] = True

    async def _cancel_async() -> Dict[str, Any]:
        broker = adapter_cls(
            api_key=api_key,
            api_secret=api_secret,
            account_id=account_id,
        )

        try:
            connected = await broker.connect()
            summary["connected"] = bool(connected)
            if not connected:
                summary["status"] = "connect_failed"
                return summary

            cancel_report = await broker.cancel_all_open_orders(limit=safe_limit)
            summary["status"] = str(cancel_report.get("status") or "ok")
            summary["openOrders"] = int(cancel_report.get("openOrders") or 0)
            summary["cancelled"] = int(cancel_report.get("cancelled") or 0)
            summary["failed"] = int(cancel_report.get("failed") or 0)
            summary["error"] = cancel_report.get("error")
            return summary
        except Exception as exc:
            summary["status"] = "error"
            summary["error"] = str(exc)
            return summary
        finally:
            try:
                await broker.disconnect()
            except Exception:
                pass

    try:
        return asyncio.run(_cancel_async())
    except RuntimeError:
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(_cancel_async())
        finally:
            loop.close()


def _suspend_runtime_services() -> Dict[str, Any]:
    """Best-effort stop for local scheduler after kill switch activation."""
    actions: Dict[str, Any] = {
        "schedulerStopRequested": False,
        "schedulerWasRunning": False,
        "schedulerStopped": False,
        "pendingOrderCancelRequested": False,
        "pendingOrdersBefore": 0,
        "pendingOrdersCancelled": 0,
        "pendingOrdersAfter": 0,
        "brokerOpenOrderCancelRequested": False,
        "brokerOpenOrdersFound": 0,
        "brokerOpenOrdersCancelled": 0,
        "brokerOpenOrdersFailed": 0,
        "brokerOpenOrderCancelSummary": None,
        "errors": [],
    }

    try:
        from src.api import server as api_server

        scheduler = getattr(api_server, "_scheduler", None)
        if scheduler is not None:
            actions["schedulerStopRequested"] = True
            thread = getattr(scheduler, "_thread", None)
            was_running = bool(thread and thread.is_alive())
            actions["schedulerWasRunning"] = was_running

            if was_running:
                scheduler.stop(timeout=2.0)
                thread_after = getattr(scheduler, "_thread", None)
                actions["schedulerStopped"] = not bool(thread_after and thread_after.is_alive())
            else:
                actions["schedulerStopped"] = True
        else:
            actions["schedulerStopped"] = True

        execution_manager = getattr(api_server, "_execution_manager", None)
        if execution_manager is not None:
            actions["pendingOrderCancelRequested"] = True

            try:
                pending_before = list(execution_manager.get_pending_orders() or [])
            except Exception:
                pending_before = []

            actions["pendingOrdersBefore"] = len(pending_before)

            try:
                if hasattr(execution_manager, "cancel_all_pending_orders"):
                    cancelled = execution_manager.cancel_all_pending_orders(
                        reason="kill_switch"
                    )
                else:
                    cancelled = 0
            except Exception as exc:
                cancelled = 0
                actions["errors"].append(str(exc))

            actions["pendingOrdersCancelled"] = int(cancelled or 0)

            try:
                pending_after = list(execution_manager.get_pending_orders() or [])
            except Exception:
                pending_after = []
            actions["pendingOrdersAfter"] = len(pending_after)

        broker_cancel_summary = _cancel_live_broker_open_orders(limit=200)
        actions["brokerOpenOrderCancelRequested"] = bool(
            broker_cancel_summary.get("requested")
        )
        actions["brokerOpenOrdersFound"] = int(
            broker_cancel_summary.get("openOrders") or 0
        )
        actions["brokerOpenOrdersCancelled"] = int(
            broker_cancel_summary.get("cancelled") or 0
        )
        actions["brokerOpenOrdersFailed"] = int(
            broker_cancel_summary.get("failed") or 0
        )
        actions["brokerOpenOrderCancelSummary"] = broker_cancel_summary
        if broker_cancel_summary.get("error"):
            actions["errors"].append(str(broker_cancel_summary["error"]))
    except Exception as exc:
        actions["errors"].append(str(exc))

    return actions


def _celery_queue_backlog_snapshot() -> Dict[str, Any]:
    enabled = str(os.getenv("AUTOSAHAM_USE_CELERY", "")).strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    if not enabled:
        return {
            "enabled": False,
            "available": False,
            "connectedWorkers": [],
            "reservedCount": 0,
            "scheduledCount": 0,
            "activeCount": 0,
            "backlogEstimate": 0,
        }

    try:
        from src.tasks import app as celery_app

        inspector = celery_app.control.inspect(timeout=0.75)
        reserved = inspector.reserved() or {}
        scheduled = inspector.scheduled() or {}
        active = inspector.active() or {}

        workers = sorted(set(reserved.keys()) | set(scheduled.keys()) | set(active.keys()))
        reserved_count = sum(len(items or []) for items in reserved.values())
        scheduled_count = sum(len(items or []) for items in scheduled.values())
        active_count = sum(len(items or []) for items in active.values())

        return {
            "enabled": True,
            "available": True,
            "connectedWorkers": workers,
            "reservedCount": int(reserved_count),
            "scheduledCount": int(scheduled_count),
            "activeCount": int(active_count),
            "backlogEstimate": int(reserved_count + scheduled_count),
        }
    except Exception as exc:
        return {
            "enabled": True,
            "available": False,
            "connectedWorkers": [],
            "reservedCount": 0,
            "scheduledCount": 0,
            "activeCount": 0,
            "backlogEstimate": 0,
            "error": str(exc),
        }


def _ws_backplane_health_snapshot() -> Dict[str, Any]:
    try:
        from src.api.event_queue import get_backplane_health

        return get_backplane_health()
    except Exception as exc:
        return {
            "instanceId": None,
            "queueDepth": 0,
            "queueCapacity": 0,
            "seenEventCacheSize": 0,
            "seenEventCacheCapacity": 0,
            "backplane": {
                "enabled": False,
                "channel": None,
                "redisUrlConfigured": False,
                "redisConnected": False,
                "subscriberReady": False,
                "initAttempted": False,
                "lastError": str(exc),
                "lastErrorAt": None,
            },
        }


def _last_state_migration_timestamp(limit: int = 200) -> Optional[str]:
    try:
        logs = _state_store.list_ai_logs(limit=limit)
    except Exception:
        return None

    for item in logs:
        if str(item.get("eventType") or "").strip().lower() != "state_store_migration":
            continue
        candidate = str(item.get("timestamp") or "").strip()
        if candidate:
            return candidate
    return None

# ============== Routes ==============

@router.get("/portfolio", response_model=Portfolio)
async def get_portfolio():
    """Get current portfolio data from runtime broker reconciliation snapshot."""
    return await _resolve_runtime_portfolio_snapshot()

@router.post("/portfolio/refresh")
async def refresh_portfolio():
    """Trigger portfolio refresh from broker"""
    # TODO: Implement actual broker refresh
    return {"status": "refreshed", "timestamp": datetime.now().isoformat()}

@router.get("/bot/status", response_model=BotStatus)
async def get_bot_status():
    """Get runtime bot status from AI activity logs and broker connection state."""
    return await _run_blocking(_resolve_runtime_bot_status)

@router.post("/bot/start")
async def start_bot(request: Request):
    """Start the trading bot"""
    _require_admin_operation(request, "Bot start")
    _assert_kill_switch_inactive("Bot start")
    return {"status": "started", "timestamp": datetime.now().isoformat()}

@router.post("/bot/stop")
async def stop_bot(request: Request):
    """Stop the trading bot"""
    _require_admin_operation(request, "Bot stop")
    # TODO: Implement bot stop logic
    return {"status": "stopped", "timestamp": datetime.now().isoformat()}

@router.post("/bot/pause")
async def pause_bot(request: Request):
    """Pause the trading bot"""
    _require_admin_operation(request, "Bot pause")
    # TODO: Implement bot pause logic
    return {"status": "paused", "timestamp": datetime.now().isoformat()}

@router.get("/signals", response_model=List[Signal])
async def get_signals(limit: int = 10):
    """Get top trading signals from ML models"""
    safe_limit = max(1, min(50, int(limit)))
    settings = _state_store.get_user_settings(_default_user_settings)
    preferred_universe = settings.get("preferredUniverse", [])

    def _filter_forex_crypto(items: List[Signal]) -> List[Signal]:
        filtered: List[Signal] = []
        for item in items:
            market = _detect_market_from_symbol(item.symbol)
            if market in {"forex", "crypto"}:
                filtered.append(item)
        return filtered

    transformer_signals = await _run_blocking(
        _infer_signals_from_transformer,
        safe_limit,
        preferred_universe,
    )
    if transformer_signals:
        filtered_transformer = _filter_forex_crypto(transformer_signals)
        if filtered_transformer:
            return filtered_transformer[:safe_limit]

    fallback_signals = await _run_blocking(
        _build_fallback_signals,
        safe_limit,
        preferred_universe,
    )
    filtered_fallback = _filter_forex_crypto(fallback_signals)
    if filtered_fallback:
        return filtered_fallback[:safe_limit]

    return [
        Signal(
            id=1,
            symbol="EURUSD=X",
            name="EUR/USD",
            signal="HOLD",
            confidence=0.5,
            reason="No valid Forex/Crypto model output is available yet; fallback signal is neutral.",
            predictedMove="+0.00%",
            riskLevel="Medium",
            sector="Forex",
            currentPrice=1.0,
            targetPrice=1.0,
            timestamp=datetime.now().isoformat(),
        )
    ][:safe_limit]

@router.get("/market/sentiment", response_model=MarketSentiment)
async def get_market_sentiment():
    """Get market sentiment from realtime global news signals."""
    news_items = _fetch_global_market_news(limit=20)
    sentiment = _aggregate_news_sentiment(news_items)

    return MarketSentiment(
        overallSentiment=float(sentiment["overallSentiment"]),
        sentiment=str(sentiment["sentiment"]),
        score=int(sentiment["score"]),
        sourceBreakdown=sentiment["sourceBreakdown"],
        recentNews=news_items[:8],
    )


@router.get("/market/universe")
async def get_market_universe(limit: int = 80, market: str = "forex"):
    """Return dynamic symbol universe for Forex and Crypto only."""
    safe_limit = max(10, min(500, int(limit)))
    normalized_market = _normalize_market_input_strict(market, allow_all=True)
    symbols: List[str] = []

    if normalized_market in {"forex", "all"}:
        symbols.extend([_normalize_symbol_input(item, market="forex") for item in _FOREX_SYMBOLS])

    if normalized_market in {"crypto", "all"}:
        symbols.extend([_normalize_symbol_input(item, market="crypto") for item in _CRYPTO_SYMBOLS])

    unique_symbols: List[str] = []
    seen = set()
    for symbol_item in symbols:
        if not symbol_item:
            continue
        if symbol_item in seen:
            continue
        seen.add(symbol_item)
        unique_symbols.append(symbol_item)

    source_tags = ["realtime"]
    if normalized_market in {"forex", "all"}:
        source_tags.append("forex")
    if normalized_market in {"crypto", "all"}:
        source_tags.append("crypto")

    return {
        "market": normalized_market,
        "availableMarkets": ["forex", "crypto", "all"],
        "symbols": unique_symbols[:safe_limit],
        "total": len(unique_symbols),
        "source": "+".join(source_tags),
        "timestamp": datetime.now().isoformat(),
    }

@router.get("/market/sectors", response_model=List[SectorData])
async def get_sector_heatmap():
    """Get sector performance heatmap"""
    # TODO: Replace with actual sector data
    return [
        SectorData(name="Financial Services", value=12.5, color="#00DD00"),
        SectorData(name="Consumer Goods", value=8.2, color="#00DD00"),
        SectorData(name="Mining", value=-1.2, color="#FF5555"),
    ]

@router.get("/market/movers", response_model=MarketMoversResponse)
async def get_top_movers(market: str = "forex"):
    """Get top market movers from realtime candle deltas."""
    symbols_payload = await get_market_universe(limit=30, market=market)
    symbols = symbols_payload.get("symbols", []) if isinstance(symbols_payload, dict) else []

    movers: List[MarketMover] = []
    try:
        from src.data.idx_fetcher import fetch_candlesticks

        for symbol in symbols[:20]:
            payload = await fetch_candlesticks(symbol, timeframe="1d", limit=2)
            candles = (payload or {}).get("candles") or []
            if len(candles) < 2:
                continue

            prev_close = _safe_float(candles[-2].get("close"), default=None)
            last_close = _safe_float(candles[-1].get("close"), default=None)
            if prev_close is None or last_close is None or prev_close <= 0:
                continue

            change = ((last_close / prev_close) - 1.0) * 100.0
            movers.append(MarketMover(symbol=symbol, change=round(change, 2)))
    except Exception:
        pass

    if not movers:
        movers = [
            MarketMover(symbol="EURUSD=X", change=0.0),
            MarketMover(symbol="BTC-USD", change=0.0),
            MarketMover(symbol="ETH-USD", change=0.0),
        ]

    sorted_payload = _adaptive_sort([item.dict() for item in movers], key_name="change", reverse=True)
    sorted_movers = [MarketMover(**item) for item in sorted_payload]
    gainers = sorted_movers[:5]
    losers = list(sorted_movers[-5:])
    losers_payload = _adaptive_sort([item.dict() for item in losers], key_name="change", reverse=False)
    losers = [MarketMover(**item) for item in losers_payload]

    return MarketMoversResponse(gainers=gainers, losers=losers)

@router.get("/market/news")
async def get_market_news(limit: int = 10, symbol: Optional[str] = None):
    """Get latest global market news with optional symbol focus."""
    return _fetch_global_market_news(limit=limit, symbol=symbol)

@router.get("/strategies", response_model=List[Strategy])
async def get_strategies():
    """Get all trading strategies"""
    # TODO: Replace with actual strategies from DB
    return [
        Strategy(
            id=1,
            name="Momentum Breakout",
            type="momentum",
            status="ready",
            description="Captures upside continuation after confirmed volume-backed breakout.",
            icon="🚀",
            desc="Buy when price breaks key resistance with strong volume confirmation.",
            expectedReturn="+18.4% / year",
            sharpeRatio="1.42",
            maxDrawdown="-8.6%",
            rules=[
                "Price closes above 20-day resistance level",
                "Volume >= 1.5x 20-day average",
                "RSI between 55 and 75 to avoid overheat",
                "Stop loss at 4.5% below entry",
            ],
            metrics={
                "winRate": 0.61,
                "avgHoldingDays": 12,
            },
        ),
        Strategy(
            id=2,
            name="Mean Reversion Swing",
            type="mean_reversion",
            status="ready",
            description="Targets oversold rebounds in liquid Forex majors and top Crypto pairs.",
            icon="📉",
            desc="Enter on oversold pullbacks and exit near equilibrium moving average.",
            expectedReturn="+14.9% / year",
            sharpeRatio="1.27",
            maxDrawdown="-7.2%",
            rules=[
                "RSI(14) below 32 and turning up",
                "Price near lower Bollinger band",
                "Trend filter: 50-day SMA still upward",
                "Take profit near 20-day SMA reversion",
            ],
            metrics={
                "winRate": 0.67,
                "avgHoldingDays": 9,
            },
        ),
        Strategy(
            id=3,
            name="Defensive Rotation",
            type="rotation",
            status="ready",
            description="Rotates allocation toward resilient sectors during risk-off phases.",
            icon="🛡️",
            desc="Favor low-volatility and dividend sectors when market breadth weakens.",
            expectedReturn="+11.6% / year",
            sharpeRatio="1.55",
            maxDrawdown="-5.4%",
            rules=[
                "Breadth ratio < 0.9 for 3 consecutive sessions",
                "Increase consumer staples and telecom exposure",
                "Reduce cyclical weights by 20%",
                "Rebalance weekly while volatility remains elevated",
            ],
            metrics={
                "winRate": 0.7,
                "avgHoldingDays": 21,
            },
        ),
    ]


@router.post("/strategies/{strategy_id}/deploy")
async def deploy_strategy(strategy_id: int, request: Request):
    """Activate a strategy for execution workflow."""
    _require_role_operation(
        request,
        "Strategy deploy",
        allowed_roles=_parse_csv_set(
            os.getenv("AUTOSAHAM_ROLE_STRATEGY_WRITE_ROLES", "trader,developer")
        ),
    )
    _assert_kill_switch_inactive("Strategy deploy")

    strategies = await get_strategies()
    strategy = next((item for item in strategies if item.id == strategy_id), None)
    if strategy is None:
        raise HTTPException(status_code=404, detail="Strategy not found")

    active_profile = _normalize_strategy_profile_key(
        _STRATEGY_PROFILE_BY_TYPE.get(str(strategy.type or "").strip().lower())
    ) or "mean_reversion_swing"

    current_settings = _state_store.get_user_settings(_default_user_settings)
    _state_store.set_user_settings(
        {
            **current_settings,
            "aiManualStrategyProfile": active_profile,
        }
    )

    synced_regime = _sync_regime_profile_override(active_profile)

    _state_store.append_ai_log(
        level="info",
        event_type="strategy_deploy",
        message=(
            f"Strategy '{strategy.name}' deployed and locked as AI profile '{active_profile}'."
        ),
        payload={
            "strategyId": strategy.id,
            "strategyName": strategy.name,
            "strategyType": strategy.type,
            "strategyProfile": active_profile,
            "manualOverride": True,
        },
    )

    return {
        "success": True,
        "status": "deployed",
        "strategy": strategy,
        "activeProfile": active_profile,
        "manualOverride": True,
        "regime": synced_regime,
        "deployedAt": datetime.now().isoformat(),
    }


@router.post("/strategies/{strategy_id}/backtest")
async def backtest_strategy(
    strategy_id: int,
    request: Request,
    payload: Optional[Dict[str, Any]] = None,
):
    """Queue a strategy backtest run and return execution metadata."""
    _require_role_operation(
        request,
        "Strategy backtest",
        allowed_roles=_parse_csv_set(
            os.getenv("AUTOSAHAM_ROLE_STRATEGY_WRITE_ROLES", "trader,developer")
        ),
    )
    _assert_kill_switch_inactive("Strategy backtest")

    strategies = await get_strategies()
    strategy = next((item for item in strategies if item.id == strategy_id), None)
    if strategy is None:
        raise HTTPException(status_code=404, detail="Strategy not found")

    run_config = payload or {}
    period = str(run_config.get("period") or "1y")
    benchmark = str(run_config.get("benchmark") or "^JKSE")

    _state_store.append_ai_log(
        level="info",
        event_type="strategy_backtest",
        message=f"Backtest started for '{strategy.name}' ({period}).",
        payload={
            "strategyId": strategy.id,
            "period": period,
            "benchmark": benchmark,
        },
    )

    return {
        "success": True,
        "status": "running",
        "strategy": strategy,
        "period": period,
        "benchmark": benchmark,
        "startedAt": datetime.now().isoformat(),
    }

@router.get("/trades", response_model=List[Trade])
async def get_trade_logs():
    """Get trade history"""
    # TODO: Replace with actual trade logs from DB
    return []

@router.get("/portfolio/health", response_model=PortfolioHealth)
async def get_portfolio_health():
    """Get portfolio health score and analysis"""
    # TODO: Replace with actual health calculation
    return PortfolioHealth(
        score=78,
        rating="Good",
        factors={
            "diversification": 82,
            "riskBalance": 75,
            "profitability": 68,
            "momentum": 81,
            "volatility": 72
        },
        recommendation="Portfolio is well-diversified with good momentum."
    )

@router.get("/activity", response_model=List[Activity])
async def get_recent_activity(limit: int = 10):
    """Get recent trading activity"""
    # TODO: Replace with actual activity log from DB
    return []

@router.get("/reports/performance")
async def get_performance_report(period: str = "today"):
    """Get performance report for specified period"""
    # TODO: Implement actual performance report generation
    return {
        "period": period,
        "totalP_L": 875000,
        "percentP_L": 0.7,
        "trades": 12,
        "winRate": 0.75,
        "generatedAt": datetime.now().isoformat()
    }


@router.get("/user/settings")
async def get_user_settings():
    """Return persisted user settings for frontend settings page."""
    return _state_store.get_user_settings(_default_user_settings)


@router.put("/user/settings")
async def update_user_settings(payload: Dict[str, Any], request: Request):
    """Update user settings in encrypted SQLite storage.

    Accept partial payloads so profile/settings pages can update safely without
    resetting unrelated values to defaults.
    """
    _require_role_operation(
        request,
        "User settings update",
        allowed_roles=_parse_csv_set(
            os.getenv("AUTOSAHAM_ROLE_SETTINGS_WRITE_ROLES", "viewer,trader,developer")
        ),
    )

    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Invalid settings payload")

    current_settings = _state_store.get_user_settings(_default_user_settings)
    allowed_keys = set(_default_user_settings.keys())
    sanitized_payload = {
        key: value
        for key, value in payload.items()
        if key in allowed_keys
    }

    if "aiManualStrategyProfile" in sanitized_payload:
        sanitized_payload["aiManualStrategyProfile"] = (
            _normalize_strategy_profile_key(sanitized_payload.get("aiManualStrategyProfile"))
            or "auto"
        )

    next_settings = {
        **current_settings,
        **sanitized_payload,
    }
    saved = _state_store.set_user_settings(next_settings)

    if "aiManualStrategyProfile" in sanitized_payload:
        synced_regime = _sync_regime_profile_override(saved.get("aiManualStrategyProfile"))
        profile_mode = "manual" if synced_regime.get("manualProfileOverride") else "auto"
        _state_store.append_ai_log(
            level="info",
            event_type="ai_profile_override",
            message=f"AI profile mode updated to {profile_mode}.",
            payload={
                "mode": profile_mode,
                "strategyProfile": synced_regime.get("strategyProfile"),
                "profileSource": synced_regime.get("profileSource"),
            },
        )

    _state_store.append_ai_log(
        level="info",
        event_type="profile_update",
        message="User settings updated and persisted.",
        payload={"theme": saved.get("theme"), "riskLevel": saved.get("riskLevel")},
    )
    return saved


@router.post("/ai/profile/reset")
async def reset_ai_profile_override(request: Request):
    """Reset AI strategy profile mode back to automatic regime routing."""
    _require_role_operation(
        request,
        "AI profile reset",
        allowed_roles=_parse_csv_set(
            os.getenv("AUTOSAHAM_ROLE_STRATEGY_WRITE_ROLES", "trader,developer")
        ),
    )

    current_settings = _state_store.get_user_settings(_default_user_settings)
    saved_settings = _state_store.set_user_settings(
        {
            **current_settings,
            "aiManualStrategyProfile": "auto",
        }
    )
    synced_regime = _sync_regime_profile_override("auto")

    _state_store.append_ai_log(
        level="info",
        event_type="ai_profile_reset",
        message="AI profile override reset to automatic regime router.",
        payload={
            "mode": "auto",
            "strategyProfile": synced_regime.get("strategyProfile"),
            "profileSource": synced_regime.get("profileSource"),
        },
    )

    return {
        "success": True,
        "mode": "auto",
        "settings": saved_settings,
        "regime": synced_regime,
        "updatedAt": datetime.now().isoformat(),
    }


@router.get("/brokers/available", response_model=List[BrokerProvider])
async def get_available_brokers():
    """Return broker integrations available in current environment."""
    feature_flags = {
        item["provider"]: item
        for item in _state_store.list_feature_flags()
    }

    providers: List[BrokerProvider] = []
    for provider in _available_broker_providers:
        flag = feature_flags.get(
            provider.id,
            {
                "liveEnabled": False,
                "paperEnabled": True,
                "integrationReady": provider.integrationReady,
            },
        )
        providers.append(
            BrokerProvider(
                id=provider.id,
                name=provider.name,
                country=provider.country,
                supportsPaper=provider.supportsPaper,
                supportsLive=provider.supportsLive,
                integrationReady=bool(flag.get("integrationReady", provider.integrationReady)),
                paperFeatureEnabled=bool(flag.get("paperEnabled", True)),
                liveFeatureEnabled=bool(flag.get("liveEnabled", False)),
            )
        )

    return providers


@router.get("/brokers/feature-flags", response_model=List[BrokerFeatureFlag])
async def get_broker_feature_flags():
    """Return feature flag state for each broker provider."""
    return _state_store.list_feature_flags()


@router.get("/system/kill-switch")
async def get_kill_switch_state():
    """Return global kill switch state."""
    return _kill_switch_state()


@router.post("/system/kill-switch/activate")
async def activate_kill_switch(
    request: Request,
    payload: Optional[KillSwitchPayload] = None,
):
    """Activate global kill switch and halt new trading actions."""
    reason = str((payload.reason if payload else "") or "Manual emergency stop").strip()
    actor = _authorize_kill_switch_actor(request, payload)
    now_iso = datetime.now().isoformat()
    runtime_actions = await _run_blocking(_suspend_runtime_services)

    current_state = _kill_switch_state()
    updated_state = _state_store.set_system_control(
        {
            **current_state,
            "killSwitchActive": True,
            "reason": reason,
            "activatedBy": actor,
            "activatedAt": current_state.get("activatedAt") or now_iso,
        }
    )

    _state_store.append_ai_log(
        level="critical",
        event_type="kill_switch_activated",
        message=f"Global kill switch activated by {actor}.",
        payload={
            "reason": reason,
            "actor": actor,
            "runtimeActions": runtime_actions,
        },
    )
    _emit_kill_switch_event(True, reason, actor)

    return {
        "status": "activated",
        "killSwitch": updated_state,
        "runtimeActions": runtime_actions,
    }


@router.post("/system/kill-switch/deactivate")
async def deactivate_kill_switch(
    request: Request,
    payload: Optional[KillSwitchPayload] = None,
):
    """Deactivate global kill switch and allow trading actions again."""
    reason = str((payload.reason if payload else "") or "Manual resume").strip()
    actor = _authorize_kill_switch_actor(request, payload)

    current_state = _kill_switch_state()
    updated_state = _state_store.set_system_control(
        {
            **current_state,
            "killSwitchActive": False,
            "reason": reason,
            "activatedBy": actor,
            "activatedAt": None,
        }
    )

    _state_store.append_ai_log(
        level="info",
        event_type="kill_switch_deactivated",
        message=f"Global kill switch deactivated by {actor}.",
        payload={
            "reason": reason,
            "actor": actor,
        },
    )
    _emit_kill_switch_event(False, reason, actor)

    return {
        "status": "deactivated",
        "killSwitch": updated_state,
    }


@router.get("/system/state-store/status")
async def get_state_store_status():
    """Inspect migration readiness across SQLite, Redis, and PostgreSQL backends."""
    return _state_store.get_state_migration_status()


@router.get("/system/migration-control-center")
async def get_migration_control_center():
    """Read-only operational view for migration, queue backlog, and kill switch state."""
    state_store_status = _state_store.get_state_migration_status()
    kill_switch = _kill_switch_state()
    broker_connection = _state_store.get_broker_connection(_default_broker_connection)

    ws_health = await _run_blocking(_ws_backplane_health_snapshot)
    celery_backlog = await _run_blocking(_celery_queue_backlog_snapshot)
    scheduler_status = await _run_blocking(_runtime_scheduler_status)
    execution_status = await _run_blocking(_runtime_execution_status)
    quota_snapshots = list_quota_usage_snapshots(limit=5)

    websocket_queue = {
        "depth": int(ws_health.get("queueDepth") or 0),
        "capacity": int(ws_health.get("queueCapacity") or 0),
        "seenCacheSize": int(ws_health.get("seenEventCacheSize") or 0),
        "seenCacheCapacity": int(ws_health.get("seenEventCacheCapacity") or 0),
    }

    return {
        "status": "ok",
        "timestamp": datetime.now().isoformat(),
        "lastStateStoreMigrationAt": _last_state_migration_timestamp(limit=200),
        "killSwitch": kill_switch,
        "stateStore": state_store_status,
        "queueBacklog": {
            "celery": celery_backlog,
            "websocket": websocket_queue,
        },
        "websocketBackplane": ws_health.get("backplane", {}),
        "quotaUsage": {
            "trackedUsers": len(quota_snapshots),
            "topUsers": quota_snapshots,
        },
        "runtime": {
            "scheduler": scheduler_status,
            "execution": execution_status,
            "brokerConnection": broker_connection,
        },
    }


@router.get("/system/quota/usage")
async def get_quota_usage(
    request: Request,
    scope: str = "self",
    user: Optional[str] = None,
    limit: int = 100,
):
    """Read quota usage counters for authenticated user (or all users for admins)."""
    session_context = _require_role_operation(
        request,
        "Quota usage read",
        allowed_roles=_parse_csv_set(
            os.getenv(
                "AUTOSAHAM_ROLE_QUOTA_READ_ROLES",
                "viewer,trader,developer,admin",
            )
        ),
    )

    requester = str(session_context.get("username") or "").strip().lower() or "anonymous"
    requester_role = str(session_context.get("role") or "viewer").strip().lower()
    requester_tier = resolve_tier_from_role(requester_role)
    admin_session = _is_admin_session(session_context)

    normalized_scope = str(scope or "self").strip().lower()
    requested_user = str(user or "").strip().lower()

    if normalized_scope == "all":
        if not admin_session:
            raise HTTPException(
                status_code=403,
                detail="Quota all-users view requires admin role.",
            )

        safe_limit = max(1, min(5000, int(limit)))
        snapshots = list_quota_usage_snapshots(limit=safe_limit)
        return {
            "status": "ok",
            "scope": "all",
            "total": len(snapshots),
            "usage": snapshots,
        }

    target_user = requested_user or requester
    if target_user != requester and not admin_session:
        raise HTTPException(
            status_code=403,
            detail="Quota self view can only access your own usage.",
        )

    snapshot = get_quota_usage_snapshot(
        target_user,
        fallback_tier=requester_tier,
    )
    return {
        "status": "ok",
        "scope": "self",
        "usage": snapshot,
    }


@router.get("/system/execution/pending-orders")
async def get_execution_pending_orders(limit: int = 200):
    """Read-only snapshot for runtime pending orders tracked by execution manager."""
    safe_limit = max(1, min(1000, int(limit)))
    execution_status = await _run_blocking(_runtime_execution_status)

    pending_orders: List[Dict[str, Any]] = []
    try:
        from src.api import server as api_server

        execution_manager = getattr(api_server, "_execution_manager", None)
        if execution_manager is not None and hasattr(execution_manager, "get_pending_orders"):
            pending_orders = list(execution_manager.get_pending_orders() or [])
    except Exception:
        pending_orders = []

    return {
        "status": "ok",
        "timestamp": datetime.now().isoformat(),
        "execution": execution_status,
        "total": len(pending_orders),
        "pendingOrders": pending_orders[:safe_limit],
    }


@router.post("/system/execution/orders")
async def submit_execution_order(payload: ExecutionOrderPayload, request: Request):
    """Submit a runtime order request (market or limit) to execution manager."""
    _require_role_operation(
        request,
        "Execution order submit",
        allowed_roles=_parse_csv_set(
            os.getenv("AUTOSAHAM_ROLE_EXECUTION_WRITE_ROLES", "trader,developer")
        ),
    )

    execution_manager = _runtime_execution_manager()
    if execution_manager is None:
        raise HTTPException(
            status_code=503,
            detail="Execution manager is unavailable.",
        )

    symbol = str(payload.symbol or "").strip().upper()
    if not symbol:
        raise HTTPException(status_code=400, detail="symbol is required")

    if not _is_supported_market_symbol(symbol, market="all"):
        raise HTTPException(
            status_code=400,
            detail="Only Forex/Crypto symbols are supported (examples: EURUSD=X, BTC-USD).",
        )

    symbol_market = "forex" if _is_forex_symbol(symbol) else "crypto"
    symbol = _normalize_symbol_input(symbol, market=symbol_market)

    side = str(payload.side or "").strip().lower()
    if side not in {"buy", "sell"}:
        raise HTTPException(status_code=400, detail="side must be buy or sell")

    qty = float(payload.qty or 0.0)
    if (not math.isfinite(qty)) or qty <= 0:
        raise HTTPException(status_code=400, detail="qty must be > 0")

    order_type = str(payload.orderType or "limit").strip().lower()
    if order_type not in {"limit", "market"}:
        raise HTTPException(status_code=400, detail="orderType must be limit or market")

    previous_close = (
        float(payload.previousClose)
        if payload.previousClose is not None
        else None
    )

    if order_type == "limit":
        if payload.limitPrice is None:
            raise HTTPException(status_code=400, detail="limitPrice is required for limit order")

        limit_price = float(payload.limitPrice)
        if limit_price <= 0:
            raise HTTPException(status_code=400, detail="limitPrice must be > 0")

        if not hasattr(execution_manager, "place_limit_order"):
            raise HTTPException(status_code=503, detail="Execution manager does not support limit orders.")

        submission = execution_manager.place_limit_order(
            symbol=symbol,
            side=side,
            qty=qty,
            limit_price=limit_price,
            previous_close=previous_close,
        )
    else:
        candidate_price = payload.marketPrice
        if candidate_price is None:
            candidate_price = payload.limitPrice
        if candidate_price is None:
            raise HTTPException(
                status_code=400,
                detail="marketPrice (or limitPrice fallback) is required for market order",
            )

        market_price = float(candidate_price)
        if market_price <= 0:
            raise HTTPException(status_code=400, detail="marketPrice must be > 0")

        if not hasattr(execution_manager, "place_order"):
            raise HTTPException(status_code=503, detail="Execution manager does not support market orders.")

        submission = execution_manager.place_order(
            symbol=symbol,
            side=side,
            qty=qty,
            price=market_price,
            previous_close=previous_close,
        )

    if not isinstance(submission, dict):
        raise HTTPException(status_code=500, detail="Unexpected execution response type")

    accepted = str(submission.get("status") or "").strip().lower() in {
        "filled",
        "pending",
        "queued",
    }
    if not accepted:
        reason = str(submission.get("reason") or "order_rejected")
        raise HTTPException(status_code=400, detail=reason)

    _state_store.append_ai_log(
        level="info",
        event_type="execution_order_submit",
        message=f"{order_type.upper()} order submitted for {symbol} ({side.upper()} x{qty}).",
        payload={
            "symbol": symbol,
            "side": side,
            "qty": qty,
            "orderType": order_type,
            "status": submission.get("status"),
            "orderId": submission.get("order_id") or submission.get("id"),
        },
    )

    return {
        "status": "ok",
        "accepted": True,
        "orderType": order_type,
        "symbol": symbol,
        "side": side,
        "qty": qty,
        "submission": submission,
        "timestamp": datetime.now().isoformat(),
    }


@router.post("/system/state-store/migrate")
async def migrate_state_store(request: Request, payload: StateMigrationPayload):
    """Run backend state migration from SQLite to Redis/PostgreSQL."""
    _require_admin_operation(request, "State store migration")

    result = _state_store.run_state_backend_migration(
        clear_sqlite=bool(payload.clearSqlite)
    )

    _state_store.append_ai_log(
        level="info",
        event_type="state_store_migration",
        message="State store backend migration executed.",
        payload={
            "clearSqlite": bool(payload.clearSqlite),
            "secureMigrated": result.get("secureState", {}).get("migrated", 0),
            "aiLogsMigrated": result.get("aiLogs", {}).get("migrated", 0),
        },
    )
    return result


@router.put("/brokers/feature-flags/{provider_id}", response_model=BrokerFeatureFlag)
async def update_broker_feature_flag(
    provider_id: str,
    payload: BrokerFeatureFlagUpdatePayload,
    request: Request,
):
    """Update live/paper feature flags for broker providers."""
    _require_admin_operation(request, "Broker feature-flag update")

    provider_key = provider_id.strip().lower()
    valid_provider_ids = {provider.id for provider in _available_broker_providers}
    if provider_key not in valid_provider_ids:
        raise HTTPException(status_code=404, detail="Broker provider not found")

    updated = _state_store.upsert_feature_flag(
        provider_key,
        live_enabled=payload.liveEnabled,
        paper_enabled=payload.paperEnabled,
        integration_ready=payload.integrationReady,
    )

    _state_store.append_ai_log(
        level="info",
        event_type="broker_feature_flag",
        message=f"Broker feature flag updated for {provider_key}.",
        payload=updated,
    )

    return updated


@router.get("/broker/connection")
async def get_broker_connection():
    """Return current broker connection state."""
    return _state_store.get_broker_connection(_default_broker_connection)


@router.post("/broker/connect")
async def connect_broker(payload: BrokerConnectPayload, request: Request):
    """Connect broker using provider feature flags with paper fallback."""
    _require_admin_operation(request, "Broker connect")

    provider_key = (payload.provider or "").strip().lower()
    provider = next((item for item in _available_broker_providers if item.id == provider_key), None)
    if not provider:
        raise HTTPException(status_code=404, detail="Broker provider not found")

    if provider.id not in _INSTITUTIONAL_BROKER_IDS:
        raise HTTPException(
            status_code=400,
            detail="Only institutional broker providers are allowed for realtime AI/ML execution.",
        )

    requested_mode = (payload.tradingMode or "paper").lower()
    if requested_mode not in {"paper", "live"}:
        raise HTTPException(status_code=400, detail="Invalid trading mode")

    account_id = payload.accountId.strip()
    if not account_id:
        raise HTTPException(status_code=400, detail="Account ID is required")

    feature_flags = {
        item["provider"]: item
        for item in _state_store.list_feature_flags()
    }
    provider_flags = feature_flags.get(
        provider.id,
        {
            "liveEnabled": False,
            "paperEnabled": True,
            "integrationReady": provider.integrationReady,
        },
    )

    if not bool(provider_flags.get("paperEnabled", True)) and requested_mode == "paper":
        raise HTTPException(status_code=400, detail="Paper mode is disabled for this provider")

    effective_mode = "paper"
    fallback_reason = None
    execution_backend = "paper"

    if requested_mode == "live":
        live_enabled = bool(provider_flags.get("liveEnabled", False))
        integration_ready = bool(provider_flags.get("integrationReady", False))
        supports_live = bool(provider.supportsLive)

        if live_enabled and integration_ready and supports_live:
            effective_mode = "live"
            execution_backend = f"{provider.id}_live"
        else:
            effective_mode = "paper"
            fallback_reason = (
                "Live trading is disabled or not ready for this provider. "
                "Connection has been safely downgraded to paper mode."
            )

    if effective_mode == "paper" and not bool(provider_flags.get("paperEnabled", True)):
        raise HTTPException(status_code=400, detail="Paper fallback is disabled for this provider")

    masked_key = "****"
    api_key = (payload.apiKey or "").strip()
    api_secret = (payload.apiSecret or "").strip()
    if api_key:
        masked_key = f"{api_key[:4]}****"

    if api_key or api_secret:
        _state_store.set_broker_credentials(
            {
                "provider": provider.id,
                "accountId": account_id,
                "apiKey": api_key or None,
                "apiSecret": api_secret or None,
                "storedAt": datetime.now().isoformat(),
            }
        )
    else:
        _state_store.clear_broker_credentials()

    next_connection = _state_store.set_broker_connection(
        {
            "connected": True,
            "provider": provider.id,
            "providerName": provider.name,
            "accountId": account_id,
            "requestedMode": requested_mode,
            "tradingMode": effective_mode,
            "maskedApiKey": masked_key,
            "executionBackend": execution_backend,
            "fallbackReason": fallback_reason,
            "lastSync": datetime.now().isoformat(),
            "features": {
                "paperTrading": bool(provider_flags.get("paperEnabled", True)),
                "liveTrading": bool(provider_flags.get("liveEnabled", False)),
                "autoWithdraw": False,
            },
        }
    )

    current_settings = _state_store.get_user_settings(_default_user_settings)
    _state_store.set_user_settings(
        {
            **current_settings,
            "brokerProvider": provider.id,
            "brokerName": provider.name,
            "brokerAccountId": account_id,
            "apiKey": masked_key,
            "tradingMode": effective_mode,
        }
    )

    _state_store.append_ai_log(
        level="info" if not fallback_reason else "warning",
        event_type="broker_connect",
        message=(
            f"Broker {provider.name} connected in {effective_mode} mode"
            if not fallback_reason
            else f"Broker {provider.name} requested live mode but fallback to paper was applied"
        ),
        payload={
            "provider": provider.id,
            "requestedMode": requested_mode,
            "effectiveMode": effective_mode,
            "fallbackReason": fallback_reason,
        },
    )

    return {
        "status": "connected",
        "connection": next_connection,
    }


@router.post("/broker/disconnect")
async def disconnect_broker(request: Request):
    """Disconnect active broker account and keep app in paper-only mode."""
    _require_admin_operation(request, "Broker disconnect")

    disconnected_state = _state_store.set_broker_connection(
        {
            "connected": False,
            "provider": None,
            "providerName": None,
            "accountId": None,
            "requestedMode": "paper",
            "tradingMode": "paper",
            "maskedApiKey": None,
            "executionBackend": "paper",
            "fallbackReason": None,
            "lastSync": datetime.now().isoformat(),
            "features": {
                "paperTrading": True,
                "liveTrading": False,
                "autoWithdraw": False,
            },
        }
    )

    current_settings = _state_store.get_user_settings(_default_user_settings)
    _state_store.set_user_settings(
        {
            **current_settings,
            "brokerAccountId": "",
            "apiKey": "****",
            "tradingMode": "paper",
        }
    )

    _state_store.append_ai_log(
        level="info",
        event_type="broker_disconnect",
        message="Broker connection disconnected and execution switched to paper mode.",
        payload={},
    )

    _state_store.clear_broker_credentials()

    return {
        "status": "disconnected",
        "connection": disconnected_state,
    }


@router.get("/ai/projection/{symbol}", response_model=AIProjectionResponse)
async def get_ai_projection(
    symbol: str,
    timeframe: str = "1d",
    horizon: int = 16,
    market: Optional[str] = None,
):
    """Build AI projection curve aligned to selected chart timeframe."""
    if market is None:
        normalized_market = _detect_market_from_symbol(symbol)
        if normalized_market not in {"forex", "crypto"}:
            raise HTTPException(
                status_code=400,
                detail="Only Forex/Crypto symbols are supported for AI projection.",
            )
    else:
        normalized_market = _normalize_market_input_strict(market, allow_all=True)

    normalized_symbol = _normalize_symbol_input(symbol, market=normalized_market)
    if not normalized_symbol:
        raise HTTPException(status_code=400, detail="Symbol is required")

    if normalized_market == "all":
        normalized_market = _detect_market_from_symbol(normalized_symbol)
        if normalized_market not in {"forex", "crypto"}:
            raise HTTPException(
                status_code=400,
                detail="Only Forex/Crypto symbols are supported for AI projection.",
            )
        normalized_symbol = _normalize_symbol_input(normalized_symbol, market=normalized_market)

    if not _is_supported_market_symbol(normalized_symbol, market=normalized_market):
        raise HTTPException(
            status_code=400,
            detail="Only Forex/Crypto symbols are supported for AI projection.",
        )

    normalized_timeframe = str(timeframe or "1d").strip().lower()
    if normalized_timeframe not in _TIMEFRAME_SECONDS:
        raise HTTPException(status_code=400, detail="Unsupported timeframe")

    safe_horizon = max(4, min(120, int(horizon)))
    seed = await _run_blocking(
        _predict_projection_seed,
        normalized_symbol,
        normalized_market,
    )

    market_seed = None
    seed_confidence = float(max(0.0, min(1.0, seed.get("confidence") or 0.0)))
    seed_return = float(seed.get("expected_return") or 0.0)

    # If model confidence is weak, blend in live market momentum to avoid noisy low-confidence outputs.
    if (seed_confidence < 0.40) or (abs(seed_return) < 0.0005):
        market_seed = await _resolve_market_projection_seed(normalized_symbol, normalized_timeframe)

    if market_seed:
        if seed.get("source") == "transformer":
            base_conf = float(max(0.0, min(1.0, seed.get("confidence") or 0.0)))
            market_conf = float(max(0.0, min(1.0, market_seed.get("confidence") or 0.0)))
            base_ret = float(seed.get("expected_return") or 0.0)
            market_ret = float(market_seed.get("expected_return") or 0.0)

            seed["model_confidence"] = seed.get("model_confidence", base_conf)
            seed["confidence"] = max(0.35, min(0.90, (0.55 * base_conf) + (0.45 * market_conf)))
            seed["expected_return"] = max(-0.30, min(0.30, (0.6 * base_ret) + (0.4 * market_ret)))
            seed["predicted_move"] = f"{seed['expected_return'] * 100:+.2f}%"
            seed["signal"] = _signal_from_expected_return(
                seed["expected_return"],
                seed["confidence"],
                return_levels=[-0.06, 0.06],
            )
            seed["reason"] = (
                "Transformer output had weak certainty and was stabilized using realtime "
                "market momentum confirmation."
            )
            seed["source"] = "transformer+market"
        else:
            seed = market_seed

    generated_at = datetime.now().isoformat()
    anchor_time = int(datetime.now().timestamp())
    anchor_price = float(max(0.01, seed.get("current_price") or 0.0))

    latest_candle = await _resolve_latest_candle_anchor(normalized_symbol, normalized_timeframe)
    if latest_candle:
        anchor_time = int(latest_candle["time"])
        anchor_price = float(max(0.01, latest_candle["price"]))

    expected_return = float(seed.get("expected_return") or 0.0)
    confidence = float(max(0.0, min(1.0, seed.get("confidence") or 0.0)))
    model_confidence = seed.get("model_confidence")
    model_confidence = (
        float(max(0.0, min(1.0, model_confidence)))
        if model_confidence is not None
        else None
    )

    news_context = _fetch_global_market_news(limit=6, symbol=normalized_symbol)
    if not news_context:
        news_context = _build_generated_news_context(
            symbol=normalized_symbol,
            timeframe=normalized_timeframe,
            signal=str(seed.get("signal") or "HOLD"),
            expected_return=expected_return,
            confidence=confidence,
        )
    sentiment = _aggregate_news_sentiment(news_context)
    sentiment_score = float(sentiment.get("overallSentiment") or 0.0)

    # Mildly adjust projection with global sentiment while keeping model direction dominant.
    sentiment_adjustment = max(-0.02, min(0.02, sentiment_score * 0.015))
    expected_return = max(-0.30, min(0.30, expected_return + sentiment_adjustment))

    # Horizon scaling makes projection horizon visibly meaningful on both slope and target.
    horizon_factor = max(0.50, min(2.50, safe_horizon / 16.0))
    expected_return = max(-0.30, min(0.30, expected_return * horizon_factor))

    confidence_boost = 0.0
    if (expected_return >= 0 and sentiment_score >= 0) or (expected_return < 0 and sentiment_score < 0):
        confidence_boost = 0.04
    elif abs(sentiment_score) > 0.35:
        confidence_boost = -0.04

    confidence = max(0.55, min(0.94, confidence + confidence_boost))

    learning_summary = _apply_projection_learning(
        symbol=normalized_symbol,
        timeframe=normalized_timeframe,
        confidence=confidence,
        expected_return=expected_return,
        anchor_time=anchor_time,
        anchor_price=anchor_price,
        horizon=safe_horizon,
    )
    confidence = float(max(0.55, min(0.96, learning_summary.get("calibratedConfidence") or confidence)))

    target_price = float(max(0.0, anchor_price * (1.0 + expected_return)))
    predicted_move = f"{expected_return * 100:+.2f}%"

    signal = str(seed.get("signal") or "HOLD")
    signal = _signal_from_expected_return(expected_return, confidence, return_levels=[-0.06, 0.06])
    confidence_label = _confidence_label(confidence)

    rationale = _build_ai_rationale(
        symbol=normalized_symbol,
        timeframe=normalized_timeframe,
        horizon=safe_horizon,
        signal=signal,
        expected_return=expected_return,
        confidence=confidence,
        source=str(seed.get("source") or "fallback"),
        sentiment=sentiment,
        news_items=news_context,
        learning_summary=learning_summary,
    )

    reason = " ".join(rationale).strip()
    if not reason:
        reason = "AI rationale generated from realtime market and global macro context."

    projection = _build_projection_points(
        base_time=anchor_time,
        current_price=anchor_price,
        expected_return=expected_return,
        timeframe=normalized_timeframe,
        horizon=safe_horizon,
    )

    await _emit_projection_notification(
        {
            **seed,
            "symbol": normalized_symbol,
            "signal": signal,
            "confidence": confidence,
            "expected_return": expected_return,
            "source": seed.get("source") or "fallback",
        },
        timeframe=normalized_timeframe,
    )

    regime_state = _state_store.get_regime_state(_default_regime_state)

    return AIProjectionResponse(
        symbol=normalized_symbol,
        timeframe=normalized_timeframe,
        horizon=safe_horizon,
        source=str(seed.get("source") or "fallback"),
        architecture=seed.get("architecture"),
        generatedAt=generated_at,
        signal=signal,
        reason=reason,
        confidence=confidence,
        modelConfidence=model_confidence,
        confidenceLabel=confidence_label,
        expectedReturn=expected_return,
        predictedMove=str(predicted_move),
        currentPrice=anchor_price,
        targetPrice=target_price,
        baseTime=anchor_time,
        projection=projection,
        regime=regime_state,
        rationale=rationale,
        newsContext=news_context,
    )


@router.get("/ai/overview")
async def get_ai_overview():
    """Return AI workflow status, learning pipeline state, and key ML metrics."""
    settings = _state_store.get_user_settings(_default_user_settings)
    regime_state = _state_store.get_regime_state(_default_regime_state)
    model_meta = await _run_blocking(_get_latest_model_artifact)
    dataset_path = _resolve_dataset_csv_path()
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    dataset_rows = await _run_blocking(_count_csv_rows, dataset_path)
    dataset_updated_at = None
    if os.path.exists(dataset_path):
        dataset_updated_at = datetime.fromtimestamp(os.path.getmtime(dataset_path)).isoformat()
    recent_logs = _state_store.list_ai_logs(limit=50)
    bot_status = await _run_blocking(_resolve_runtime_bot_status)

    warning_count = sum(1 for item in recent_logs if item.get("level") == "warning")
    error_count = sum(1 for item in recent_logs if item.get("level") == "error")

    regime_label = str(regime_state.get("regime") or "UNKNOWN").upper()
    regime_status = "ready" if regime_label != "UNKNOWN" else "warming_up"

    return {
        "status": "running",
        "lastInferenceAt": recent_logs[0]["timestamp"] if recent_logs else None,
        "regime": regime_state,
        "model": {
            "artifact": model_meta.get("artifact"),
            "lastTrainedAt": model_meta.get("lastTrainedAt"),
            "architecture": model_meta.get("architecture"),
            "source": model_meta.get("source"),
            "selectionScore": model_meta.get("score"),
            "datasetRows": dataset_rows,
            "datasetSource": os.path.relpath(dataset_path, project_root),
            "datasetUpdatedAt": dataset_updated_at,
            "isRealtimeDataset": False,
            "preferredUniverse": settings.get("preferredUniverse", []),
        },
        "learningPipeline": [
            {
                "stage": "Data ingestion",
                "status": "running",
                "detail": "Collecting Forex/Crypto candles and sentiment features.",
            },
            {
                "stage": "Feature engineering",
                "status": "running",
                "detail": "Computing technical indicators and microstructure factors.",
            },
            {
                "stage": "Model scoring",
                "status": "ready" if model_meta.get("artifact") else "warming_up",
                "detail": "Serving confidence score and signal direction.",
            },
            {
                "stage": "Regime router",
                "status": regime_status,
                "detail": (
                    f"Market regime {regime_label} routed to "
                    f"{regime_state.get('primaryAgent') or 'scalper_agent'}."
                ),
            },
            {
                "stage": "Execution gateway",
                "status": "running",
                "detail": "Routing approved signals to broker adapter.",
            },
        ],
        "metrics": {
            "activeTrades": bot_status.activeTrades,
            "winRate": bot_status.winRate,
            "warningEvents": warning_count,
            "errorEvents": error_count,
            "processedEvents": len(recent_logs),
        },
    }


@router.get("/ai/regime")
async def get_ai_regime_status():
    """Return latest persisted market regime route snapshot."""
    return _state_store.get_regime_state(_default_regime_state)


@router.get("/ai/logs")
async def get_ai_logs(limit: int = 100):
    """Return AI activity logs for monitoring panel."""
    return _state_store.list_ai_logs(limit=limit)


@router.post("/ai/logs")
async def create_ai_log(payload: AILogPayload, request: Request):
    """Append an AI activity log entry."""
    _require_role_operation(
        request,
        "AI logs write",
        allowed_roles=_parse_csv_set(
            os.getenv("AUTOSAHAM_ROLE_AI_LOG_WRITE_ROLES", "trader,developer")
        ),
    )

    return _state_store.append_ai_log(
        level=payload.level,
        event_type=payload.eventType,
        message=payload.message,
        payload=payload.payload,
    )
