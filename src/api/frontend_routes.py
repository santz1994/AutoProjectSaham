"""
Additional API routes for AutoSaham frontend integration.
Contains endpoints for portfolio, bot status, signals, strategies, trades, and market data.
"""

from fastapi import APIRouter, HTTPException
from typing import Optional, List, Dict, Any
from pydantic import BaseModel
from datetime import datetime, timedelta

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


class BrokerConnectPayload(BaseModel):
    provider: str
    accountId: str
    apiKey: Optional[str] = ""
    tradingMode: str = "paper"


_user_settings_store: Dict[str, Any] = {
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
        supportsLive=False,
        integrationReady=False,
    ),
    BrokerProvider(
        id="motiontrade",
        name="MotionTrade (MNC Sekuritas)",
        supportsPaper=True,
        supportsLive=False,
        integrationReady=False,
    ),
    BrokerProvider(
        id="indopremier",
        name="Indo Premier",
        supportsPaper=True,
        supportsLive=False,
        integrationReady=False,
    ),
]

_broker_connection_store: Dict[str, Any] = {
    "connected": False,
    "provider": None,
    "providerName": None,
    "accountId": None,
    "tradingMode": "paper",
    "maskedApiKey": None,
    "lastSync": None,
    "features": {
        "paperTrading": True,
        "liveTrading": False,
        "autoWithdraw": False,
    },
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
    return _user_settings_store


@router.put("/user/settings")
async def update_user_settings(payload: UserSettings):
    """Update user settings in memory (placeholder for DB-backed persistence)."""
    _user_settings_store.update(payload.model_dump())
    _user_settings_store["updatedAt"] = datetime.now().isoformat()
    return _user_settings_store


@router.get("/brokers/available", response_model=List[BrokerProvider])
async def get_available_brokers():
    """Return broker integrations available in current environment."""
    return _available_broker_providers


@router.get("/broker/connection")
async def get_broker_connection():
    """Return current broker connection state."""
    return _broker_connection_store


@router.post("/broker/connect")
async def connect_broker(payload: BrokerConnectPayload):
    """Connect selected broker in safe paper mode by default.

    This route currently persists connection settings in memory only.
    """
    provider = next((p for p in _available_broker_providers if p.id == payload.provider), None)
    if not provider:
        raise HTTPException(status_code=404, detail="Broker provider not found")

    requested_mode = (payload.tradingMode or "paper").lower()
    if requested_mode not in {"paper", "live"}:
        raise HTTPException(status_code=400, detail="Invalid trading mode")

    if requested_mode == "live":
        raise HTTPException(
            status_code=400,
            detail="Live trading integration is not enabled yet. Use paper mode for now.",
        )

    account_id = payload.accountId.strip()
    if not account_id:
        raise HTTPException(status_code=400, detail="Account ID is required")

    masked_key = "****"
    api_key = (payload.apiKey or "").strip()
    if api_key:
        masked_key = f"{api_key[:4]}****"

    _broker_connection_store.update(
        {
            "connected": True,
            "provider": provider.id,
            "providerName": provider.name,
            "accountId": account_id,
            "tradingMode": requested_mode,
            "maskedApiKey": masked_key,
            "lastSync": datetime.now().isoformat(),
        }
    )

    _user_settings_store.update(
        {
            "brokerProvider": provider.id,
            "brokerName": provider.name,
            "brokerAccountId": account_id,
            "apiKey": masked_key,
            "tradingMode": requested_mode,
            "updatedAt": datetime.now().isoformat(),
        }
    )

    return {
        "status": "connected",
        "connection": _broker_connection_store,
    }


@router.post("/broker/disconnect")
async def disconnect_broker():
    """Disconnect active broker account and keep app in paper-only mode."""
    _broker_connection_store.update(
        {
            "connected": False,
            "provider": None,
            "providerName": None,
            "accountId": None,
            "tradingMode": "paper",
            "maskedApiKey": None,
            "lastSync": datetime.now().isoformat(),
        }
    )

    _user_settings_store.update(
        {
            "brokerAccountId": "",
            "apiKey": "****",
            "tradingMode": "paper",
            "updatedAt": datetime.now().isoformat(),
        }
    )

    return {
        "status": "disconnected",
        "connection": _broker_connection_store,
    }
