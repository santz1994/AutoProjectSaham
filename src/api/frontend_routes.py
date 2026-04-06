"""
Additional API routes for AutoSaham frontend integration.
Contains endpoints for portfolio, bot status, signals, strategies, trades, and market data.
"""

import csv
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
    theme: str = "dark"
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
    "theme": "dark",
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


def _count_csv_rows(csv_path: str) -> int:
    if not os.path.exists(csv_path):
        return 0

    with open(csv_path, "r", encoding="utf-8") as file:
        reader = csv.reader(file)
        count = -1  # exclude header row
        for count, _ in enumerate(reader):
            pass

    return max(0, count)


def _get_latest_model_artifact() -> Dict[str, Any]:
    models_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "models"))
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
        }

    return {
        "artifact": latest_name,
        "lastTrainedAt": datetime.fromtimestamp(latest_ts).isoformat(),
    }

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
    # TODO: Replace with actual signals from ML pipeline
    signals = [
        Signal(
            id=1,
            symbol="INDF.JK",
            name="Indofood Sukses Makmur",
            signal="STRONG_BUY",
            confidence=0.92,
            reason="Volume spike 45% + Positive sentiment",
            predictedMove="+3.2%",
            riskLevel="Low-Medium",
            sector="Consumer Goods",
            currentPrice=9150,
            targetPrice=9440,
            timestamp=datetime.now().isoformat()
        )
    ]
    return signals[:limit]

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
    dataset_rows = _count_csv_rows(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "data", "dataset.csv")))
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
            "datasetRows": dataset_rows,
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
