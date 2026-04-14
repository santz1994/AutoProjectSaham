"""Configuration constants for frontend API routes."""

from __future__ import annotations

import os
from datetime import datetime
from typing import Any, Dict, List

from src.api.schemas.frontend import BrokerProvider


default_user_settings: Dict[str, Any] = {
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
    "preferredUniverse": ["EURUSD=X", "GBPUSD=X", "BTC-USD", "ETH-USD", "SOL-USD"],
    "aiDefaultMarket": "forex",
    "aiPredictionStyle": "daily_trader",
    "aiDefaultTimeframe": "15m",
    "aiProjectionHorizon": 16,
    "aiPredictionLockEnabled": True,
    "aiMonitorRefreshSeconds": 20,
    "aiManualStrategyProfile": "auto",
    "updatedAt": datetime.now().isoformat(),
}

institutional_broker_ids = {
    "indonesia-securities",
    "indopremier",
    "mandiri-sekuritas",
    "bni-sekuritas",
    "cgs-cimb",
}

available_broker_providers: List[BrokerProvider] = [
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

default_broker_connection: Dict[str, Any] = {
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

default_regime_state: Dict[str, Any] = {
    "regime": "UNKNOWN",
    "confidence": 0.0,
    "primaryAgent": "scalper_agent",
    "strategyProfile": "mean_reversion_swing",
    "manualProfileOverride": False,
    "profileSource": "regime_router",
    "riskMultiplier": 0.75,
    "trendReturn": 0.0,
    "volatility": 0.0,
    "upMoveRatio": 0.5,
    "symbols": [],
    "pricePoints": 0,
    "asOf": None,
}

default_system_control: Dict[str, Any] = {
    "killSwitchActive": False,
    "reason": None,
    "activatedAt": None,
    "activatedBy": None,
}

strategy_profile_by_type: Dict[str, str] = {
    "momentum": "momentum_breakout",
    "mean_reversion": "mean_reversion_swing",
    "rotation": "defensive_rotation",
}

profile_route_presets: Dict[str, Dict[str, Any]] = {
    "momentum_breakout": {
        "primaryAgent": "bull_agent",
        "riskMultiplier": 1.0,
    },
    "mean_reversion_swing": {
        "primaryAgent": "scalper_agent",
        "riskMultiplier": 0.75,
    },
    "defensive_rotation": {
        "primaryAgent": "bear_agent",
        "riskMultiplier": 0.55,
    },
}

default_broker_feature_flags = [
    {"provider": "indonesia-securities", "liveEnabled": os.getenv("BROKER_LIVE_INDONESIA_SECURITIES", "1") == "1", "paperEnabled": True, "integrationReady": True},
    {"provider": "indopremier", "liveEnabled": os.getenv("BROKER_LIVE_INDOPREMIER", "1") == "1", "paperEnabled": True, "integrationReady": True},
    {"provider": "mandiri-sekuritas", "liveEnabled": os.getenv("BROKER_LIVE_MANDIRI", "1") == "1", "paperEnabled": True, "integrationReady": True},
    {"provider": "bni-sekuritas", "liveEnabled": os.getenv("BROKER_LIVE_BNI", "1") == "1", "paperEnabled": True, "integrationReady": True},
    {"provider": "cgs-cimb", "liveEnabled": os.getenv("BROKER_LIVE_CGS_CIMB", "1") == "1", "paperEnabled": True, "integrationReady": True},
]

symbol_name_map: Dict[str, str] = {
    "EURUSD=X": "EUR/USD",
    "GBPUSD=X": "GBP/USD",
    "USDJPY=X": "USD/JPY",
    "USDCAD=X": "USD/CAD",
    "BTC-USD": "Bitcoin",
    "ETH-USD": "Ethereum",
    "SOL-USD": "Solana",
    "BNB-USD": "BNB",
    "XRP-USD": "XRP",
}

symbol_sector_map: Dict[str, str] = {
    "EURUSD=X": "Forex",
    "GBPUSD=X": "Forex",
    "USDJPY=X": "Forex",
    "USDCAD=X": "Forex",
    "BTC-USD": "Crypto",
    "ETH-USD": "Crypto",
    "SOL-USD": "Crypto",
    "BNB-USD": "Crypto",
    "XRP-USD": "Crypto",
}

timeframe_seconds: Dict[str, int] = {
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

market_news_fallback = [
    "EURUSD=X",
    "GBPUSD=X",
    "USDJPY=X",
    "USDCAD=X",
    "BTC-USD",
    "ETH-USD",
    "SOL-USD",
    "BNB-USD",
    "CL=F",
    "GC=F",
]

forex_symbols = [
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

crypto_symbols = [
    "BTC-USD",
    "ETH-USD",
    "SOL-USD",
    "BNB-USD",
    "XRP-USD",
    "ADA-USD",
    "DOGE-USD",
]

global_index_symbols = [
    "^GSPC",
    "^IXIC",
    "^DJI",
    "^HSI",
    "^N225",
]

market_aliases: Dict[str, str] = {
    "forex": "forex",
    "fx": "forex",
    "crypto": "crypto",
    "blockchain": "crypto",
    "all": "all",
    "multi": "all",
}
