"""Pydantic schemas for frontend API routes."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel


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
    killSwitchActive: bool = False
    killSwitchReason: Optional[str] = None
    performanceToday: dict = {}


class Signal(BaseModel):
    id: int
    symbol: str
    name: str
    signal: str
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
    regime: Dict[str, Any] = {}
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
    type: str
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
    preferredUniverse: List[str] = ["EURUSD=X", "GBPUSD=X", "BTC-USD", "ETH-USD", "SOL-USD"]
    aiDefaultMarket: str = "forex"
    aiPredictionStyle: str = "daily_trader"
    aiDefaultTimeframe: str = "15m"
    aiProjectionHorizon: int = 16
    aiPredictionLockEnabled: bool = True
    aiMonitorRefreshSeconds: int = 20
    aiManualStrategyProfile: str = "auto"


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
    apiSecret: Optional[str] = ""
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


class StateMigrationPayload(BaseModel):
    clearSqlite: bool = False


class KillSwitchPayload(BaseModel):
    reason: Optional[str] = None
    actor: Optional[str] = None
    activatedBy: Optional[str] = None
    challengeCode: Optional[str] = None


class AILogPayload(BaseModel):
    level: str = "info"
    eventType: str = "manual"
    message: str
    payload: Dict[str, Any] = {}


class ExecutionOrderPayload(BaseModel):
    symbol: str
    side: str
    qty: float
    orderType: str = "limit"
    limitPrice: Optional[float] = None
    marketPrice: Optional[float] = None
    previousClose: Optional[float] = None
