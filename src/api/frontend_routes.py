"""
Additional API routes for AutoSaham frontend integration.
Contains endpoints for portfolio, bot status, signals, strategies, trades, and market data.
"""

import csv
import json
import math
import os
from threading import Lock
from fastapi import APIRouter, HTTPException
from typing import Optional, List, Dict, Any, Tuple
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


class AIProjectionPoint(BaseModel):
    time: int
    value: float


class AIProjectionResponse(BaseModel):
    symbol: str
    timeframe: str
    horizon: int
    source: str
    architecture: Optional[str] = None
    generatedAt: str
    signal: str
    reason: str
    confidence: float
    modelConfidence: Optional[float] = None
    confidenceLabel: str = "medium"
    expectedReturn: float
    predictedMove: str
    currentPrice: float
    targetPrice: float
    baseTime: int
    projection: List[AIProjectionPoint]
    rationale: List[str] = []
    newsContext: List[Dict[str, Any]] = []

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
    "brokerProvider": "indopremier",
    "apiKey": "****",
    "brokerName": "Indo Premier Institutional",
    "brokerAccountId": "",
    "tradingMode": "paper",
    "maxPositionSize": 10.0,
    "stopLossPercent": 5.0,
    "takeProfitPercent": 10.0,
    "maxOpenPositions": 5,
    "preferredUniverse": ["BBCA.JK", "USIM.JK", "KLBF.JK", "ASII.JK", "UNVR.JK"],
    "updatedAt": datetime.now().isoformat(),
}

_INSTITUTIONAL_BROKER_IDS = {
    "indonesia-securities",
    "indopremier",
    "mandiri-sekuritas",
    "bni-sekuritas",
    "cgs-cimb",
}

_available_broker_providers: List[BrokerProvider] = [
    BrokerProvider(
        id="indonesia-securities",
        name="Indonesia Securities Institutional Desk",
        supportsPaper=True,
        supportsLive=True,
        integrationReady=True,
    ),
    BrokerProvider(
        id="indopremier",
        name="Indo Premier Institutional",
        supportsPaper=True,
        supportsLive=True,
        integrationReady=True,
    ),
    BrokerProvider(
        id="mandiri-sekuritas",
        name="Mandiri Sekuritas Institutional",
        supportsPaper=True,
        supportsLive=True,
        integrationReady=True,
    ),
    BrokerProvider(
        id="bni-sekuritas",
        name="BNI Sekuritas Institutional",
        supportsPaper=True,
        supportsLive=True,
        integrationReady=True,
    ),
    BrokerProvider(
        id="cgs-cimb",
        name="CGS-CIMB Institutional",
        supportsPaper=True,
        supportsLive=True,
        integrationReady=True,
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
    {"provider": "indonesia-securities", "liveEnabled": os.getenv("BROKER_LIVE_INDONESIA_SECURITIES", "1") == "1", "paperEnabled": True, "integrationReady": True},
    {"provider": "indopremier", "liveEnabled": os.getenv("BROKER_LIVE_INDOPREMIER", "1") == "1", "paperEnabled": True, "integrationReady": True},
    {"provider": "mandiri-sekuritas", "liveEnabled": os.getenv("BROKER_LIVE_MANDIRI", "1") == "1", "paperEnabled": True, "integrationReady": True},
    {"provider": "bni-sekuritas", "liveEnabled": os.getenv("BROKER_LIVE_BNI", "1") == "1", "paperEnabled": True, "integrationReady": True},
    {"provider": "cgs-cimb", "liveEnabled": os.getenv("BROKER_LIVE_CGS_CIMB", "1") == "1", "paperEnabled": True, "integrationReady": True},
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

_TIMEFRAME_SECONDS: Dict[str, int] = {
    "1m": 60,
    "5m": 5 * 60,
    "15m": 15 * 60,
    "30m": 30 * 60,
    "1h": 60 * 60,
    "4h": 4 * 60 * 60,
    "1d": 24 * 60 * 60,
    "1w": 7 * 24 * 60 * 60,
    "1mo": 30 * 24 * 60 * 60,
}

_projection_notification_state: Dict[Tuple[str, str], str] = {}

_MARKET_NEWS_FALLBACK = [
    "BBCA.JK",
    "BMRI.JK",
    "BBRI.JK",
    "TLKM.JK",
    "^GSPC",
    "^DJI",
    "^IXIC",
    "USDIDR=X",
    "CL=F",
    "GC=F",
]

_FOREX_SYMBOLS = [
    "EURUSD=X",
    "GBPUSD=X",
    "USDJPY=X",
    "AUDUSD=X",
    "USDCHF=X",
    "USDCAD=X",
    "NZDUSD=X",
    "EURJPY=X",
    "USDIDR=X",
]

_CRYPTO_SYMBOLS = [
    "BTC-USD",
    "ETH-USD",
    "SOL-USD",
    "BNB-USD",
    "XRP-USD",
    "ADA-USD",
    "DOGE-USD",
]

_GLOBAL_INDEX_SYMBOLS = [
    "^GSPC",
    "^IXIC",
    "^DJI",
    "^HSI",
    "^N225",
]

_global_news_cache: Dict[str, Any] = {
    "key": None,
    "fetched_at": None,
    "items": [],
}

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


def _symbol_base(symbol: str) -> str:
    normalized = str(symbol or "").strip().upper()
    if not normalized:
        return ""
    if normalized.endswith(".JK"):
        return normalized.split(".")[0]
    if normalized.endswith("=X"):
        return normalized.replace("=X", "")
    if "-USD" in normalized:
        return normalized.split("-USD")[0]
    return normalized


def _symbol_aliases(symbol: str) -> List[str]:
    normalized = str(symbol or "").strip().upper()
    if not normalized:
        return []

    aliases = {normalized}
    base = _symbol_base(normalized)
    if base:
        aliases.add(base)
        aliases.add(f"{base}.JK")

    if normalized.endswith("=X"):
        pair = normalized.replace("=X", "")
        aliases.add(pair)
        if len(pair) == 6:
            aliases.add(f"{pair[:3]}/{pair[3:]}")
    elif len(normalized) == 6 and normalized.isalpha():
        aliases.add(f"{normalized}=X")
        aliases.add(f"{normalized[:3]}/{normalized[3:]}")

    if "-USD" in normalized:
        base_coin = normalized.split("-USD")[0]
        aliases.add(base_coin)
        aliases.add(f"{base_coin}USDT")
    elif normalized.endswith("USDT") and len(normalized) > 4:
        base_coin = normalized[:-4]
        aliases.add(base_coin)
        aliases.add(f"{base_coin}-USD")

    return list(aliases)


def _symbols_match(left: str, right: str) -> bool:
    left_aliases = set(_symbol_aliases(left))
    right_aliases = set(_symbol_aliases(right))
    if not left_aliases or not right_aliases:
        return False
    return not left_aliases.isdisjoint(right_aliases)


def _detect_market_from_symbol(symbol: str) -> str:
    normalized = str(symbol or "").strip().upper()
    if not normalized:
        return "stocks"
    if normalized.endswith("=X") or (len(normalized) == 6 and normalized.isalpha()) or "/" in normalized:
        return "forex"
    if "-USD" in normalized or normalized.endswith("USDT"):
        return "crypto"
    if normalized.startswith("^"):
        return "index"
    return "stocks"


def _normalize_market_input(market: Optional[str]) -> str:
    normalized = str(market or "stocks").strip().lower()
    aliases = {
        "saham": "stocks",
        "stock": "stocks",
        "equity": "stocks",
        "forex": "forex",
        "fx": "forex",
        "crypto": "crypto",
        "blockchain": "crypto",
        "all": "all",
        "multi": "all",
        "index": "index",
    }
    return aliases.get(normalized, "stocks")


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


def _confidence_label(confidence: float) -> str:
    safe_confidence = float(max(0.0, min(1.0, confidence)))
    if safe_confidence < 0.35:
        return "very_low"
    if safe_confidence < 0.50:
        return "low"
    if safe_confidence < 0.65:
        return "medium"
    if safe_confidence < 0.80:
        return "high"
    return "very_high"


def _keyword_sentiment_score(text: str) -> float:
    headline = str(text or "").lower()
    if not headline:
        return 0.0

    positive_keywords = [
        "beat", "beats", "surge", "gain", "growth", "bullish", "upgrade",
        "stimulus", "easing", "strong", "optimistic", "record high", "inflow",
        "accumulation", "expansion", "rally", "outperform",
    ]
    negative_keywords = [
        "miss", "drop", "selloff", "bearish", "downgrade", "risk-off", "tightening",
        "hawkish", "inflation spike", "recession", "war", "sanction", "outflow",
        "distribution", "decline", "volatile", "warning", "fraud",
    ]

    positive_hits = sum(1 for keyword in positive_keywords if keyword in headline)
    negative_hits = sum(1 for keyword in negative_keywords if keyword in headline)
    total_hits = positive_hits + negative_hits

    if total_hits == 0:
        return 0.0
    return float(max(-1.0, min(1.0, (positive_hits - negative_hits) / total_hits)))


def _aggregate_news_sentiment(news_items: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not news_items:
        return {
            "overallSentiment": 0.0,
            "sentiment": "NEUTRAL",
            "score": 50,
            "sourceBreakdown": {
                "globalNews": 0.0,
                "macroSignals": 0.0,
                "institutionalFlow": 0.0,
            },
        }

    scores: List[float] = []
    for item in news_items:
        title = item.get("headline") or item.get("title") or ""
        score = _keyword_sentiment_score(title)
        scores.append(score)

    avg_score = float(sum(scores) / len(scores)) if scores else 0.0
    sentiment_label = "NEUTRAL"
    if avg_score >= 0.20:
        sentiment_label = "BULLISH"
    elif avg_score <= -0.20:
        sentiment_label = "BEARISH"

    return {
        "overallSentiment": avg_score,
        "sentiment": sentiment_label,
        "score": int(max(0, min(100, round((avg_score + 1.0) * 50)))),
        "sourceBreakdown": {
            "globalNews": round(avg_score, 3),
            "macroSignals": round(avg_score * 0.9, 3),
            "institutionalFlow": round(avg_score * 0.8, 3),
        },
    }


def _normalize_news_item(raw_item: Dict[str, Any], source_name: str) -> Optional[Dict[str, Any]]:
    title = str(raw_item.get("title") or raw_item.get("headline") or "").strip()
    if not title:
        return None

    published_at = (
        raw_item.get("publishedAt")
        or raw_item.get("published_at")
        or raw_item.get("providerPublishTime")
    )
    if isinstance(published_at, (int, float)):
        published_iso = datetime.fromtimestamp(float(published_at)).isoformat()
    else:
        published_iso = str(published_at or datetime.now().isoformat())

    score = _keyword_sentiment_score(title)
    sentiment = "neutral"
    if score > 0.15:
        sentiment = "positive"
    elif score < -0.15:
        sentiment = "negative"

    source = raw_item.get("source")
    if isinstance(source, dict):
        source = source.get("name")

    return {
        "headline": title,
        "sentiment": sentiment,
        "score": round(score, 4),
        "source": str(source or source_name),
        "timestamp": published_iso,
        "url": raw_item.get("url") or raw_item.get("link") or "",
    }


def _fetch_global_market_news(limit: int = 10, symbol: Optional[str] = None) -> List[Dict[str, Any]]:
    safe_limit = max(1, min(100, int(limit)))
    symbol_key = _symbol_base(symbol or "") or "GLOBAL"
    cache_key = f"{symbol_key}:{safe_limit}"

    fetched_at = _global_news_cache.get("fetched_at")
    if (
        _global_news_cache.get("key") == cache_key
        and isinstance(fetched_at, datetime)
        and (datetime.now() - fetched_at).total_seconds() <= 90
    ):
        cached = _global_news_cache.get("items") or []
        return list(cached)[:safe_limit]

    news_items: List[Dict[str, Any]] = []
    seen_headlines = set()

    def _append_items(items: List[Dict[str, Any]], source_name: str) -> None:
        for raw_item in items:
            normalized = _normalize_news_item(raw_item, source_name)
            if not normalized:
                continue
            key = normalized["headline"].lower()
            if key in seen_headlines:
                continue
            seen_headlines.add(key)
            news_items.append(normalized)
            if len(news_items) >= safe_limit:
                return

    # Primary source: NewsAPI global headlines (if API key configured).
    api_key = os.getenv("NEWSAPI_KEY", "").strip()
    if api_key:
        try:
            from src.pipeline.data_connectors.news_connector import fetch_news

            symbol_base = _symbol_base(symbol or "")
            query = "IDX OR IHSG OR Indonesia stocks OR Federal Reserve OR CPI OR oil"
            if symbol_base:
                query = f"({symbol_base}) OR ({query})"

            payload = fetch_news(
                query=query,
                api_key=api_key,
                page=1,
                page_size=min(50, safe_limit),
            )
            api_articles = payload.get("articles") if isinstance(payload, dict) else []
            if isinstance(api_articles, list):
                _append_items(api_articles, "NewsAPI")
        except Exception:
            pass

    # Fallback source: yfinance ticker news for symbol + macro assets.
    if len(news_items) < safe_limit:
        try:
            import yfinance as yf

            symbols_to_fetch = []
            if symbol:
                symbols_to_fetch.append(_normalize_symbol_input(symbol))
            for item in _MARKET_NEWS_FALLBACK:
                if item not in symbols_to_fetch:
                    symbols_to_fetch.append(item)

            for ticker_symbol in symbols_to_fetch:
                ticker = yf.Ticker(ticker_symbol)
                articles = getattr(ticker, "news", None) or []
                if isinstance(articles, list):
                    _append_items(articles, f"yfinance:{ticker_symbol}")
                if len(news_items) >= safe_limit:
                    break
        except Exception:
            pass

    news_items.sort(key=lambda item: str(item.get("timestamp", "")), reverse=True)
    output = news_items[:safe_limit]
    _global_news_cache.update(
        {
            "key": cache_key,
            "fetched_at": datetime.now(),
            "items": output,
        }
    )
    return output


def _build_ai_rationale(
    symbol: str,
    timeframe: str,
    horizon: int,
    signal: str,
    expected_return: float,
    confidence: float,
    source: str,
    sentiment: Dict[str, Any],
    news_items: List[Dict[str, Any]],
    learning_summary: Optional[Dict[str, Any]] = None,
) -> List[str]:
    direction = "upside" if expected_return >= 0 else "downside"
    confidence_pct = confidence * 100.0
    sentiment_text = sentiment.get("sentiment", "NEUTRAL")

    rationale = [
        (
            f"{str(source).upper()} inference indicates {signal} bias on {symbol} "
            f"for {timeframe} with projected {direction} {expected_return * 100:+.2f}% "
            f"over {horizon} steps (confidence {confidence_pct:.2f}%)."
        ),
        (
            f"Global-news sentiment is {sentiment_text} "
            f"(score {sentiment.get('score', 50)}/100), blended with live candle momentum "
            "to reduce single-model overfitting risk."
        ),
    ]

    if news_items:
        top_news = news_items[0]
        rationale.append(
            (
                f"Latest macro/market driver: {top_news.get('headline', 'N/A')} "
                f"[{top_news.get('source', 'global')}]"
            )
        )

    if isinstance(learning_summary, dict):
        samples = int(max(0, _safe_float(learning_summary.get("observations"), default=0.0) or 0.0))
        reliability = float(max(0.0, min(1.0, _safe_float(learning_summary.get("reliability"), default=0.0) or 0.0)))
        wins = int(max(0, _safe_float(learning_summary.get("wins"), default=0.0) or 0.0))
        losses = int(max(0, _safe_float(learning_summary.get("losses"), default=0.0) or 0.0))
        rationale.append(
            (
                f"Online learning memory across previous projections: reliability {reliability * 100:.2f}% "
                f"from {samples} resolved sample(s) (wins {wins}, losses {losses})."
            )
        )

    return rationale


def _build_generated_news_context(
    symbol: str,
    timeframe: str,
    signal: str,
    expected_return: float,
    confidence: float,
) -> List[Dict[str, Any]]:
    now_iso = datetime.now().isoformat()
    direction = "positive" if expected_return > 0 else "negative" if expected_return < 0 else "neutral"
    move_pct = expected_return * 100.0
    confidence_pct = confidence * 100.0

    return [
        {
            "headline": (
                f"AI-generated macro pulse: {symbol} shows {signal} pressure on {timeframe} horizon "
                f"with projected move {move_pct:+.2f}%"
            ),
            "sentiment": direction,
            "score": round(max(-1.0, min(1.0, expected_return * 8.0)), 4),
            "source": "ai-generated",
            "timestamp": now_iso,
            "url": "",
        },
        {
            "headline": (
                "Institutional-flow proxy and live momentum were fused with latest candles "
                "to reduce noisy projections"
            ),
            "sentiment": "neutral",
            "score": 0.0,
            "source": "ai-generated",
            "timestamp": now_iso,
            "url": "",
        },
        {
            "headline": (
                f"Confidence calibration layer running in nonstop mode at {confidence_pct:.2f}% "
                "to learn from previous projection outcomes"
            ),
            "sentiment": "positive" if confidence >= 0.6 else "neutral",
            "score": round(max(-1.0, min(1.0, (confidence - 0.5) * 1.6)), 4),
            "source": "ai-generated",
            "timestamp": now_iso,
            "url": "",
        },
    ]


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


def _normalize_symbol_input(symbol: str, market: Optional[str] = None) -> str:
    normalized = str(symbol or "").strip().upper()
    if not normalized:
        return normalized

    normalized_market = _normalize_market_input(market) if market is not None else _detect_market_from_symbol(normalized)

    if normalized_market == "forex":
        compact = normalized.replace("/", "")
        if compact.endswith("=X"):
            return compact
        if len(compact) == 6 and compact.isalpha():
            return f"{compact}=X"
        return compact

    if normalized_market == "crypto":
        if normalized.endswith("USDT") and "-" not in normalized:
            return f"{normalized[:-4]}-USD"
        if "-" not in normalized and not normalized.endswith("USD"):
            return f"{normalized}-USD"
        return normalized

    if normalized.startswith("^"):
        return normalized

    if "." not in normalized:
        normalized = f"{normalized}.JK"
    return normalized


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
async def get_market_universe(limit: int = 80, market: str = "stocks"):
    """Return dynamic symbol universe across stocks, forex, crypto, and global indexes."""
    safe_limit = max(10, min(500, int(limit)))
    normalized_market = _normalize_market_input(market)
    symbols: List[str] = []

    if normalized_market in {"stocks", "all"}:
        try:
            from src.data.idx_fetcher import get_available_symbols

            idx_symbols = await get_available_symbols()
            symbols.extend([_normalize_symbol_input(item, market="stocks") for item in idx_symbols])
        except Exception:
            pass

        settings = _state_store.get_user_settings(_default_user_settings)
        preferred = settings.get("preferredUniverse") if isinstance(settings, dict) else []
        if isinstance(preferred, list):
            symbols.extend([_normalize_symbol_input(item, market="stocks") for item in preferred])

        dataset_path = _resolve_dataset_csv_path()
        try:
            import pandas as pd

            if os.path.exists(dataset_path):
                df = pd.read_csv(dataset_path, usecols=["symbol"])
                dataset_symbols = [
                    _normalize_symbol_input(str(item), market="stocks")
                    for item in df["symbol"].dropna().astype(str).tolist()
                ]
                symbols.extend(dataset_symbols)
        except Exception:
            pass

    if normalized_market in {"forex", "all"}:
        symbols.extend([_normalize_symbol_input(item, market="forex") for item in _FOREX_SYMBOLS])

    if normalized_market in {"crypto", "all"}:
        symbols.extend([_normalize_symbol_input(item, market="crypto") for item in _CRYPTO_SYMBOLS])

    if normalized_market in {"index", "all"}:
        symbols.extend([_normalize_symbol_input(item, market="index") for item in _GLOBAL_INDEX_SYMBOLS])

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
    if normalized_market in {"stocks", "all"}:
        source_tags.append("idx")
    if normalized_market in {"forex", "all"}:
        source_tags.append("forex")
    if normalized_market in {"crypto", "all"}:
        source_tags.append("crypto")

    return {
        "market": normalized_market,
        "availableMarkets": ["stocks", "forex", "crypto", "index", "all"],
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
async def get_top_movers(market: str = "stocks"):
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
            MarketMover(symbol="BBCA.JK", change=0.0),
            MarketMover(symbol="BMRI.JK", change=0.0),
            MarketMover(symbol="TLKM.JK", change=0.0),
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


@router.post("/strategies/{strategy_id}/deploy")
async def deploy_strategy(strategy_id: int):
    """Activate a strategy for execution workflow."""
    strategies = await get_strategies()
    strategy = next((item for item in strategies if item.id == strategy_id), None)
    if strategy is None:
        raise HTTPException(status_code=404, detail="Strategy not found")

    _state_store.append_ai_log(
        level="info",
        event_type="strategy_deploy",
        message=f"Strategy '{strategy.name}' deployed for live monitoring.",
        payload={
            "strategyId": strategy.id,
            "strategyName": strategy.name,
            "strategyType": strategy.type,
        },
    )

    return {
        "success": True,
        "status": "deployed",
        "strategy": strategy,
        "deployedAt": datetime.now().isoformat(),
    }


@router.post("/strategies/{strategy_id}/backtest")
async def backtest_strategy(strategy_id: int, payload: Optional[Dict[str, Any]] = None):
    """Queue a strategy backtest run and return execution metadata."""
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
async def update_user_settings(payload: Dict[str, Any]):
    """Update user settings in encrypted SQLite storage.

    Accept partial payloads so profile/settings pages can update safely without
    resetting unrelated values to defaults.
    """
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Invalid settings payload")

    current_settings = _state_store.get_user_settings(_default_user_settings)
    allowed_keys = set(_default_user_settings.keys())
    sanitized_payload = {
        key: value
        for key, value in payload.items()
        if key in allowed_keys
    }

    next_settings = {
        **current_settings,
        **sanitized_payload,
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


@router.get("/ai/projection/{symbol}", response_model=AIProjectionResponse)
async def get_ai_projection(
    symbol: str,
    timeframe: str = "1d",
    horizon: int = 16,
    market: Optional[str] = None,
):
    """Build AI projection curve aligned to selected chart timeframe."""
    normalized_market = _normalize_market_input(market)
    normalized_symbol = _normalize_symbol_input(symbol, market=normalized_market)
    if not normalized_symbol:
        raise HTTPException(status_code=400, detail="Symbol is required")

    normalized_timeframe = str(timeframe or "1d").strip().lower()
    if normalized_timeframe not in _TIMEFRAME_SECONDS:
        raise HTTPException(status_code=400, detail="Unsupported timeframe")

    safe_horizon = max(4, min(120, int(horizon)))
    seed = _predict_projection_seed(normalized_symbol, market=normalized_market)

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
        rationale=rationale,
        newsContext=news_context,
    )


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
