"""
Additional API routes for AutoSaham frontend integration.
Contains endpoints for portfolio, bot status, signals, strategies, trades, and market data.
"""

import csv
import json
import os
from fastapi import APIRouter, HTTPException
from typing import Optional, List, Dict, Any
from pydantic import BaseModel
from datetime import datetime, timedelta

from src.api.state_store import SecureAppStateStore

router = APIRouter(prefix="/api", tags=["frontend"])

# ============== Models ==============

class PortfolioPosition(BaseModel):
    symbol: str
    name: str
    quantity: int
    entryPrice: float
    currentPrice: float
    totalValue: float
    p_l: float
    percentP_L: float
    sector: str
    riskScore: str

class Portfolio(BaseModel):
    totalValue: float
    totalP_L: float
    percentP_L: float
    cash: float
    purchasingPower: float
    lastUpdate: str
    positions: List[PortfolioPosition]

class BotStatus(BaseModel):
    status: str
    uptime: Optional[str] = None
    activeTrades: int = 0
    totalTradesToday: int = 0
    successfulTrades: int = 0
    failedTrades: int = 0
    winRate: float = 0.0
    lastTradeTime: Optional[str] = None
    nextAnalysisIn: Optional[str] = None
    performanceToday: dict = {}

class Signal(BaseModel):
    id: int
    symbol: str
    name: str
    signal: str  # STRONG_BUY, BUY, HOLD, SELL, STRONG_SELL
    confidence: float
    reason: str
    predictedMove: str
    riskLevel: str
    sector: str
    currentPrice: float
    targetPrice: float
    timestamp: str

class Strategy(BaseModel):
    id: int
    name: str
    type: str = "custom"
    status: str = "ready"
    description: str = ""
    icon: str = "🎯"
    desc: str = ""
    expectedReturn: str = "N/A"
    sharpeRatio: str = "N/A"
    maxDrawdown: str = "N/A"
    rules: List[str] = []
    metrics: dict = {}

class Trade(BaseModel):
    id: int
    symbol: str
    type: str  # BUY or SELL
    quantity: int
    price: float
    total: float
    status: str
    strategy: str
    signal: str
    timestamp: str

class MarketSentiment(BaseModel):
    overallSentiment: float
    sentiment: str
    score: int
    sourceBreakdown: dict
    recentNews: List[dict]

class SectorData(BaseModel):
    name: str
    value: float
    color: str

class PortfolioHealth(BaseModel):
    score: int
    rating: str
    factors: dict
    recommendation: str

class Activity(BaseModel):
    id: int
    type: str
    symbol: Optional[str] = None
    quantity: Optional[int] = None
    price: Optional[float] = None
    timestamp: str
    status: str
    signal: Optional[str] = None
    message: Optional[str] = None


class MarketMover(BaseModel):
    symbol: str
    change: float


class MarketMoversResponse(BaseModel):
    gainers: List[MarketMover]
    losers: List[MarketMover]


class UserSettings(BaseModel):
    fullName: str = "AutoSaham User"
    email: str = "user@autosaham.local"
    phone: str = ""
    theme: str = "auto"
    notifications: bool = True
    soundAlerts: bool = False
    emailReports: bool = True
    twoFactor: bool = False
    dailyReport: str = "end-of-day"
    autoTrading: bool = False
    riskLevel: str = "moderate"
    maxDrawdown: int = 15
    brokerProvider: str = "indonesia-securities"
    apiKey: str = "****"
    brokerName: str = "Indonesia Securities"
    brokerAccountId: str = ""
    tradingMode: str = "paper"
    maxPositionSize: float = 10.0
    stopLossPercent: float = 5.0
    takeProfitPercent: float = 10.0
    maxOpenPositions: int = 5
    preferredUniverse: List[str] = ["BBCA.JK", "USIM.JK", "KLBF.JK", "ASII.JK", "UNVR.JK"]


class BrokerProvider(BaseModel):
    id: str
    name: str
    country: str = "ID"
    supportsPaper: bool = True
    supportsLive: bool = False
    integrationReady: bool = False
    paperFeatureEnabled: bool = True
    liveFeatureEnabled: bool = False


class BrokerConnectPayload(BaseModel):
    provider: str
    accountId: str
    apiKey: Optional[str] = ""
    tradingMode: str = "paper"


class BrokerFeatureFlag(BaseModel):
    provider: str
    liveEnabled: bool = False
    paperEnabled: bool = True
    integrationReady: bool = False
    updatedAt: Optional[str] = None


class BrokerFeatureFlagUpdatePayload(BaseModel):
    liveEnabled: Optional[bool] = None
    paperEnabled: Optional[bool] = None
    integrationReady: Optional[bool] = None


class AILogPayload(BaseModel):
    level: str = "info"
    eventType: str = "manual"
    message: str
    payload: Dict[str, Any] = {}


_default_user_settings: Dict[str, Any] = {
    "fullName": "AutoSaham User",
    "email": "user@autosaham.local",
    "phone": "",
    "theme": "auto",
    "notifications": True,
    "soundAlerts": False,
    "emailReports": True,
    "twoFactor": False,
    "dailyReport": "end-of-day",
    "autoTrading": False,
    "riskLevel": "moderate",
    "maxDrawdown": 15,
    "brokerProvider": "indonesia-securities",
    "apiKey": "****",
    "brokerName": "Indonesia Securities",
    "brokerAccountId": "",
    "tradingMode": "paper",
    "maxPositionSize": 10.0,
    "stopLossPercent": 5.0,
    "takeProfitPercent": 10.0,
    "maxOpenPositions": 5,
    "preferredUniverse": ["BBCA.JK", "USIM.JK", "KLBF.JK", "ASII.JK", "UNVR.JK"],
    "updatedAt": datetime.now().isoformat(),
}

_available_broker_providers: List[BrokerProvider] = [
    BrokerProvider(
        id="indonesia-securities",
        name="Indonesia Securities",
        supportsPaper=True,
        supportsLive=False,
        integrationReady=False,
    ),
    BrokerProvider(
        id="ajaib",
        name="Ajaib",
        supportsPaper=True,
        supportsLive=True,
        integrationReady=True,
    ),
    BrokerProvider(
        id="motiontrade",
        name="MotionTrade (MNC Sekuritas)",
        supportsPaper=True,
        supportsLive=True,
        integrationReady=True,
    ),
    BrokerProvider(
        id="indopremier",
        name="Indo Premier",
        supportsPaper=True,
        supportsLive=False,
        integrationReady=False,
    ),
]

_default_broker_connection: Dict[str, Any] = {
    "connected": False,
    "provider": None,
    "providerName": None,
    "accountId": None,
    "tradingMode": "paper",
    "requestedMode": "paper",
    "maskedApiKey": None,
    "executionBackend": "paper",
    "fallbackReason": None,
    "lastSync": None,
    "features": {
        "paperTrading": True,
        "liveTrading": False,
        "autoWithdraw": False,
    },
}

_default_broker_feature_flags = [
    {"provider": "indonesia-securities", "liveEnabled": False, "paperEnabled": True, "integrationReady": False},
    {"provider": "ajaib", "liveEnabled": os.getenv("BROKER_LIVE_AJAIB", "0") == "1", "paperEnabled": True, "integrationReady": True},
    {"provider": "motiontrade", "liveEnabled": os.getenv("BROKER_LIVE_MOTIONTRADE", "0") == "1", "paperEnabled": True, "integrationReady": True},
    {"provider": "indopremier", "liveEnabled": False, "paperEnabled": True, "integrationReady": False},
]

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
            "message": "Feature pipeline refreshed with latest IDX market snapshot.",
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


_SYMBOL_NAME_MAP: Dict[str, str] = {
    "BBCA.JK": "Bank Central Asia",
    "TLKM.JK": "Telekomunikasi Indonesia",
    "INDF.JK": "Indofood Sukses Makmur",
    "ASII.JK": "Astra International",
    "UNVR.JK": "Unilever Indonesia",
    "KLBF.JK": "Kalbe Farma",
    "USIM.JK": "Universal Broker Basket",
}

_SYMBOL_SECTOR_MAP: Dict[str, str] = {
    "BBCA.JK": "Financial Services",
    "TLKM.JK": "Telecommunications",
    "INDF.JK": "Consumer Goods",
    "ASII.JK": "Industrials",
    "UNVR.JK": "Consumer Goods",
    "KLBF.JK": "Healthcare",
}

_transformer_runtime_cache: Dict[str, Any] = {
    "path": None,
    "mtime": None,
    "runtime": None,
}


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


def _is_within_path(candidate_path: str, root_path: str) -> bool:
    try:
        candidate_abs = os.path.abspath(candidate_path)
        root_abs = os.path.abspath(root_path)
        return os.path.commonpath([candidate_abs, root_abs]) == root_abs
    except Exception:
        return False


def _coerce_model_path(project_root: str, model_path: Optional[str]) -> Optional[str]:
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

    if not _is_within_path(candidate, project_root):
        return None
    return candidate


def _load_json_if_exists(path: str) -> Optional[Dict[str, Any]]:
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
            return payload if isinstance(payload, dict) else None
    except Exception:
        return None


def _artifact_meta(
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


def _resolve_best_walk_forward_artifact(project_root: str) -> Optional[Dict[str, Any]]:
    report_path = os.path.join(project_root, "models", "transformers", "walk_forward_report.json")
    report = _load_json_if_exists(report_path)
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

            model_path = _coerce_model_path(project_root, fold.get("model_path"))
            if not model_path:
                continue

            metrics = fold.get("metrics") or {}
            if not isinstance(metrics, dict):
                metrics = {}
            score = metrics.get("f1_macro")
            accuracy = metrics.get("accuracy")
            meta = _artifact_meta(
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


def _resolve_best_baseline_artifact(project_root: str) -> Optional[Dict[str, Any]]:
    report_path = os.path.join(project_root, "models", "transformers", "baseline_report.json")
    report = _load_json_if_exists(report_path)
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

        model_path = _coerce_model_path(project_root, payload.get("model_path"))
        if not model_path:
            continue

        metrics = payload.get("metrics") or {}
        if not isinstance(metrics, dict):
            metrics = {}
        score = metrics.get("f1_macro")
        accuracy = metrics.get("accuracy")
        meta = _artifact_meta(
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


def _resolve_latest_transformer_artifact(project_root: str) -> Optional[Dict[str, Any]]:
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

    return _artifact_meta(
        project_root,
        latest_path,
        architecture=arch,
        source="latest_pt",
        score=None,
        accuracy=None,
    )


def _resolve_best_transformer_artifact(project_root: Optional[str] = None) -> Optional[Dict[str, Any]]:
    root = project_root or _get_project_root()
    candidates = [
        _resolve_best_walk_forward_artifact(root),
        _resolve_best_baseline_artifact(root),
        _resolve_latest_transformer_artifact(root),
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


def _get_latest_model_artifact() -> Dict[str, Any]:
    project_root = _get_project_root()

    transformer_artifact = _resolve_best_transformer_artifact(project_root)
    if transformer_artifact:
        return {
            "artifact": transformer_artifact.get("artifact"),
            "lastTrainedAt": transformer_artifact.get("lastTrainedAt"),
            "architecture": transformer_artifact.get("architecture"),
            "source": transformer_artifact.get("source"),
            "score": transformer_artifact.get("score"),
        }

    models_dir = os.path.join(project_root, "models")
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


def _resolve_signal_universe(df: Any, preferred_universe: Optional[List[str]], max_symbols: int) -> List[str]:
    if "symbol" not in df.columns:
        return []

    available_symbols = [str(value) for value in df["symbol"].dropna().astype(str).tolist()]
    available_set = set(available_symbols)
    selected: List[str] = []

    for symbol in preferred_universe or []:
        normalized = str(symbol).strip()
        if normalized and normalized in available_set and normalized not in selected:
            selected.append(normalized)

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
    return str(symbol).replace(".JK", "")


def _symbol_sector(symbol: str) -> str:
    return _SYMBOL_SECTOR_MAP.get(symbol, "IDX")


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
            current_price = float(sample["current_price"])
            target_price = current_price * (1.0 + expected_return) if current_price > 0 else 0.0

            ranked_rows.append(
                {
                    "rank": confidence * (abs(expected_return) + 0.001),
                    "symbol": sample["symbol"],
                    "name": _symbol_name(sample["symbol"]),
                    "signal": signal_name,
                    "confidence": confidence,
                    "reason": (
                        f"{str(runtime['architecture']).upper()} model ({runtime['source']}) "
                        f"predicted class {predicted_label_int} with {confidence * 100:.1f}% confidence."
                    ),
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

                    rows.append(
                        {
                            "rank": confidence * (abs(expected_return) + 0.001),
                            "symbol": str(symbol),
                            "name": _symbol_name(str(symbol)),
                            "signal": signal_name,
                            "confidence": confidence,
                            "reason": (
                                "Fallback technical heuristic using momentum and SMA trend gap "
                                "while transformer signal model is unavailable."
                            ),
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
            symbol="INDF.JK",
            name="Indofood Sukses Makmur",
            signal="HOLD",
            confidence=0.5,
            reason="No valid model output is available yet; fallback signal is neutral.",
            predictedMove="+0.00%",
            riskLevel="Medium",
            sector="Consumer Goods",
            currentPrice=9150,
            targetPrice=9150,
            timestamp=datetime.now().isoformat(),
        )
    ][:safe_limit]

# ============== Temporary Data (Replace with real DB queries) ==============

def get_mock_portfolio():
    """Temporary mock data - Replace with actual broker API call"""
    return Portfolio(
        totalValue=125000000,
        totalP_L=8750000,
        percentP_L=7.5,
        cash=45000000,
        purchasingPower=112500000,
        lastUpdate=datetime.now().isoformat(),
        positions=[
            PortfolioPosition(
                symbol="BBCA.JK",
                name="Bank Central Asia",
                quantity=100,
                entryPrice=45000,
                currentPrice=46500,
                totalValue=4650000,
                p_l=150000,
                percentP_L=3.3,
                sector="Financial Services",
                riskScore="Low"
            ),
            PortfolioPosition(
                symbol="TLKM.JK",
                name="Telekomunikasi Indonesia",
                quantity=200,
                entryPrice=3400,
                currentPrice=3550,
                totalValue=710000,
                p_l=30000,
                percentP_L=4.4,
                sector="Telecommunications",
                riskScore="Low"
            ),
        ]
    )

def get_mock_bot_status():
    """Temporary mock data - Replace with actual bot state"""
    return BotStatus(
        status="running",
        uptime="14h 32m",
        activeTrades=4,
        totalTradesToday=12,
        successfulTrades=9,
        failedTrades=3,
        winRate=0.75,
        lastTradeTime=(datetime.now() - timedelta(minutes=15)).isoformat(),
        nextAnalysisIn="3m 45s",
        performanceToday={"totalP_L": 875000, "percentP_L": 0.7}
    )

# ============== Routes ==============

@router.get("/portfolio", response_model=Portfolio)
async def get_portfolio():
    """Get current portfolio data from broker"""
    # TODO: Replace with actual broker API call
    return get_mock_portfolio()

@router.post("/portfolio/refresh")
async def refresh_portfolio():
    """Trigger portfolio refresh from broker"""
    # TODO: Implement actual broker refresh
    return {"status": "refreshed", "timestamp": datetime.now().isoformat()}

@router.get("/bot/status", response_model=BotStatus)
async def get_bot_status():
    """Get current bot status and performance"""
    # TODO: Replace with actual bot status from trading engine
    return get_mock_bot_status()

@router.post("/bot/start")
async def start_bot():
    """Start the trading bot"""
    # TODO: Implement bot start logic
    return {"status": "started", "timestamp": datetime.now().isoformat()}

@router.post("/bot/stop")
async def stop_bot():
    """Stop the trading bot"""
    # TODO: Implement bot stop logic
    return {"status": "stopped", "timestamp": datetime.now().isoformat()}

@router.post("/bot/pause")
async def pause_bot():
    """Pause the trading bot"""
    # TODO: Implement bot pause logic
    return {"status": "paused", "timestamp": datetime.now().isoformat()}

@router.get("/signals", response_model=List[Signal])
async def get_signals(limit: int = 10):
    """Get top trading signals from ML models"""
    safe_limit = max(1, min(50, int(limit)))
    settings = _state_store.get_user_settings(_default_user_settings)
    preferred_universe = settings.get("preferredUniverse", [])

    transformer_signals = _infer_signals_from_transformer(
        limit=safe_limit,
        preferred_universe=preferred_universe,
    )
    if transformer_signals:
        return transformer_signals[:safe_limit]

    return _build_fallback_signals(
        limit=safe_limit,
        preferred_universe=preferred_universe,
    )[:safe_limit]

@router.get("/market/sentiment", response_model=MarketSentiment)
async def get_market_sentiment():
    """Get market sentiment analysis"""
    # TODO: Replace with actual sentiment analysis
    return MarketSentiment(
        overallSentiment=0.65,
        sentiment="BULLISH",
        score=65,
        sourceBreakdown={
            "newsAnalysis": 0.72,
            "socialMedia": 0.58,
            "technicalAnalysis": 0.68,
            "institutionalFlow": 0.62
        },
        recentNews=[
            {
                "headline": "BI Pertahankan Suku Bunga, Sinyal Positif untuk Pasar Modal",
                "sentiment": "positive",
                "source": "Reuters",
                "timestamp": (datetime.now() - timedelta(hours=2)).isoformat()
            }
        ]
    )

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
async def get_top_movers():
    """Get top market movers"""
    # TODO: Replace with actual market data
    return MarketMoversResponse(
        gainers=[
            MarketMover(symbol="BBCA.JK", change=2.41),
            MarketMover(symbol="INDF.JK", change=1.87),
            MarketMover(symbol="TLKM.JK", change=1.22),
        ],
        losers=[
            MarketMover(symbol="UNVR.JK", change=-1.53),
            MarketMover(symbol="ANTM.JK", change=-1.24),
            MarketMover(symbol="PGAS.JK", change=-0.98),
        ],
    )

@router.get("/market/news")
async def get_market_news(limit: int = 10):
    """Get latest market news"""
    # TODO: Replace with actual news feed
    return []

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
            description="Targets oversold rebounds in quality large-cap IDX names.",
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
async def update_user_settings(payload: UserSettings):
    """Update user settings in encrypted SQLite storage."""
    current_settings = _state_store.get_user_settings(_default_user_settings)
    next_settings = {
        **current_settings,
        **payload.model_dump(),
    }
    saved = _state_store.set_user_settings(next_settings)

    _state_store.append_ai_log(
        level="info",
        event_type="profile_update",
        message="User settings updated and persisted.",
        payload={"theme": saved.get("theme"), "riskLevel": saved.get("riskLevel")},
    )
    return saved


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


@router.put("/brokers/feature-flags/{provider_id}", response_model=BrokerFeatureFlag)
async def update_broker_feature_flag(provider_id: str, payload: BrokerFeatureFlagUpdatePayload):
    """Update live/paper feature flags for broker providers."""
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
async def connect_broker(payload: BrokerConnectPayload):
    """Connect broker using provider feature flags with paper fallback."""
    provider_key = (payload.provider or "").strip().lower()
    provider = next((item for item in _available_broker_providers if item.id == provider_key), None)
    if not provider:
        raise HTTPException(status_code=404, detail="Broker provider not found")

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
    if api_key:
        masked_key = f"{api_key[:4]}****"

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
async def disconnect_broker():
    """Disconnect active broker account and keep app in paper-only mode."""
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

    return {
        "status": "disconnected",
        "connection": disconnected_state,
    }


@router.get("/ai/overview")
async def get_ai_overview():
    """Return AI workflow status, learning pipeline state, and key ML metrics."""
    settings = _state_store.get_user_settings(_default_user_settings)
    model_meta = _get_latest_model_artifact()
    dataset_path = _resolve_dataset_csv_path()
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    dataset_rows = _count_csv_rows(dataset_path)
    dataset_updated_at = None
    if os.path.exists(dataset_path):
        dataset_updated_at = datetime.fromtimestamp(os.path.getmtime(dataset_path)).isoformat()
    recent_logs = _state_store.list_ai_logs(limit=50)
    bot_status = get_mock_bot_status()

    warning_count = sum(1 for item in recent_logs if item.get("level") == "warning")
    error_count = sum(1 for item in recent_logs if item.get("level") == "error")

    return {
        "status": "running",
        "lastInferenceAt": recent_logs[0]["timestamp"] if recent_logs else None,
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
                "detail": "Collecting IDX candles and sentiment features.",
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


@router.get("/ai/logs")
async def get_ai_logs(limit: int = 100):
    """Return AI activity logs for monitoring panel."""
    return _state_store.list_ai_logs(limit=limit)


@router.post("/ai/logs")
async def create_ai_log(payload: AILogPayload):
    """Append an AI activity log entry."""
    return _state_store.append_ai_log(
        level=payload.level,
        event_type=payload.eventType,
        message=payload.message,
        payload=payload.payload,
    )
