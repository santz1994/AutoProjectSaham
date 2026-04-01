"""
TradingView Chart Service for Real-time OHLCV Data
=====================================================

Provides API endpoints for lightweight-charts integration with:
- Real-time WebSocket streaming (OHLCV)
- Jakarta timezone (WIB: UTC+7) support
- IDX compliance (*.JK symbols, IDR currency)
- BEI trading hours (09:30-16:00 WIB)
- Caching for performance optimization

Author: AutoSaham Team
Version: 1.0.0
"""

import json
import logging
import asyncio
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, asdict
from enum import Enum

import pytz
import pandas as pd
from fastapi import WebSocket, HTTPException, Query
from fastapi.responses import JSONResponse

# Initialize Jakarta timezone
JAKARTA_TZ = pytz.timezone("Asia/Jakarta")
BEI_TIMEZONE = JAKARTA_TZ

# BEI Trading Hours (09:30-16:00 WIB)
BEI_OPEN_HOUR = 9
BEI_OPEN_MINUTE = 30
BEI_CLOSE_HOUR = 16
BEI_CLOSE_MINUTE = 0

logger = logging.getLogger(__name__)


class TimeFrame(str, Enum):
    """Supported timeframes for chart."""
    M1 = "1m"
    M5 = "5m"
    M15 = "15m"
    M30 = "30m"
    H1 = "1h"
    H4 = "4h"
    D1 = "1d"
    W1 = "1w"
    MN1 = "1mo"


@dataclass
class OHLCV:
    """OHLCV candle data."""
    timestamp: int  # Unix timestamp (seconds)
    open: float
    high: float
    low: float
    close: float
    volume: int
    
    def to_dict(self) -> Dict:
        """Convert to dictionary."""
        return asdict(self)
    
    def to_lightweight_charts_format(self) -> Dict:
        """Format for lightweight-charts library."""
        return {
            "time": self.timestamp,
            "open": round(self.open, 2),
            "high": round(self.high, 2),
            "low": round(self.low, 2),
            "close": round(self.close, 2),
            "volume": self.volume,
        }


@dataclass
class ChartMetadata:
    """Chart metadata and configuration."""
    symbol: str  # IDX symbol (e.g., "BBCA.JK")
    exchange: str  # "IDX" (Indonesia Stock Exchange)
    currency: str  # "IDR" (Indonesian Rupiah)
    timeframe: TimeFrame
    description: str
    decimal_places: int  # Price decimal places (typically 2)
    min_lot_size: int  # Minimum lot size (100 for IDX)
    trading_start: str  # "09:30" WIB
    trading_end: str  # "16:00" WIB
    timezone: str  # "Asia/Jakarta"
    
    def to_dict(self) -> Dict:
        """Convert to dictionary."""
        return {
            "symbol": self.symbol,
            "exchange": self.exchange,
            "currency": self.currency,
            "timeFrame": self.timeframe.value,
            "description": self.description,
            "decimalPlaces": self.decimal_places,
            "minLotSize": self.min_lot_size,
            "tradingStart": self.trading_start,
            "tradingEnd": self.trading_end,
            "timezone": self.timezone,
        }


class IDXSymbolValidator:
    """Validate IDX symbol format and properties."""
    
    IDX_SYMBOLS = {
        "BBCA.JK": {
            "name": "Bank Central Asia",
            "sector": "Financial",
            "min_price": 1000,
            "max_price": 20000,
        },
        "BMRI.JK": {
            "name": "Bank Mandiri",
            "sector": "Financial",
            "min_price": 2000,
            "max_price": 10000,
        },
        "TLKM.JK": {
            "name": "Telekomunikasi Indonesia",
            "sector": "Telecommunications",
            "min_price": 2000,
            "max_price": 4000,
        },
        "ASII.JK": {
            "name": "Astra International",
            "sector": "Automotive",
            "min_price": 5000,
            "max_price": 15000,
        },
        "INDF.JK": {
            "name": "Indofood Sukses Makmur",
            "sector": "Consumer",
            "min_price": 6000,
            "max_price": 12000,
        },
    }
    
    @staticmethod
    def validate(symbol: str) -> Tuple[bool, Optional[str]]:
        """
        Validate IDX symbol format.
        
        Args:
            symbol: Symbol to validate (e.g., "BBCA.JK")
            
        Returns:
            Tuple of (is_valid, error_message)
        """
        # Check format
        if not isinstance(symbol, str):
            return False, "Symbol must be string"
        
        symbol = symbol.upper()
        parts = symbol.split(".")
        
        if len(parts) != 2:
            return False, f"Invalid symbol format: {symbol}. Use format: XXXX.JK"
        
        code, exchange = parts
        
        if exchange != "JK":
            return False, f"Invalid exchange code: {exchange}. IDX symbols must end with .JK"
        
        if len(code) < 3 or len(code) > 5:
            return False, f"Invalid symbol code: {code}. Must be 3-5 characters"
        
        if not code.isalpha():
            return False, f"Symbol code must contain only letters: {code}"
        
        return True, None
    
    @staticmethod
    def get_metadata(symbol: str) -> ChartMetadata:
        """Get metadata for symbol."""
        symbol = symbol.upper()
        
        is_valid, error = IDXSymbolValidator.validate(symbol)
        if not is_valid:
            raise ValueError(f"Invalid symbol: {error}")
        
        # Get symbol info from known list
        symbol_info = IDXSymbolValidator.IDX_SYMBOLS.get(symbol, {
            "name": symbol,
            "sector": "Unknown",
            "min_price": 100,
            "max_price": 100000,
        })
        
        return ChartMetadata(
            symbol=symbol,
            exchange="IDX",
            currency="IDR",
            timeframe=TimeFrame.D1,
            description=symbol_info.get("name", symbol),
            decimal_places=2,
            min_lot_size=100,  # IDX minimum 100 shares
            trading_start="09:30",
            trading_end="16:00",
            timezone="Asia/Jakarta",
        )


class ChartDataCache:
    """In-memory cache for chart data."""
    
    def __init__(self, ttl_minutes: int = 5):
        """
        Initialize cache.
        
        Args:
            ttl_minutes: Time-to-live for cache entries (default 5 minutes)
        """
        self.cache: Dict[str, Dict] = {}
        self.ttl = timedelta(minutes=ttl_minutes)
    
    def get(self, key: str) -> Optional[Dict]:
        """Get cached data if not expired."""
        if key not in self.cache:
            return None
        
        data, timestamp = self.cache[key]
        
        if datetime.now() - timestamp > self.ttl:
            del self.cache[key]
            return None
        
        return data
    
    def set(self, key: str, data: Dict) -> None:
        """Cache data with timestamp."""
        self.cache[key] = (data, datetime.now())
    
    def invalidate(self, key: str = None) -> None:
        """Invalidate cache entry or entire cache."""
        if key:
            self.cache.pop(key, None)
        else:
            self.cache.clear()
    
    def clear_expired(self) -> None:
        """Remove all expired entries."""
        now = datetime.now()
        expired_keys = [
            key for key, (_, timestamp) in self.cache.items()
            if now - timestamp > self.ttl
        ]
        for key in expired_keys:
            del self.cache[key]


class OHLCVAggregator:
    """Aggregate OHLCV data for different timeframes."""
    
    @staticmethod
    def resample_to_timeframe(
        df: pd.DataFrame, 
        timeframe: TimeFrame
    ) -> List[OHLCV]:
        """
        Resample OHLCV data to target timeframe.
        
        Args:
            df: DataFrame with OHLCV data (index as datetime)
            timeframe: Target timeframe (M1, M5, M15, M30, H1, H4, D1, W1, MN1)
            
        Returns:
            List of OHLCV objects
        """
        # Resample frequency mapping
        freq_map = {
            TimeFrame.M1: "1min",
            TimeFrame.M5: "5min",
            TimeFrame.M15: "15min",
            TimeFrame.M30: "30min",
            TimeFrame.H1: "1h",
            TimeFrame.H4: "4h",
            TimeFrame.D1: "1d",
            TimeFrame.W1: "1w",
            TimeFrame.MN1: "1mo",
        }
        
        freq = freq_map.get(timeframe, "1d")
        
        # Ensure dataframe is in Jakarta timezone
        if df.index.tz is None:
            df.index = df.index.tz_localize(JAKARTA_TZ)
        else:
            df.index = df.index.tz_convert(JAKARTA_TZ)
        
        # Resample
        resampled = df.resample(freq).agg({
            "open": "first",
            "high": "max",
            "low": "min",
            "close": "last",
            "volume": "sum",
        }).dropna()
        
        # Convert to OHLCV objects
        candles = []
        for timestamp, row in resampled.iterrows():
            ohlcv = OHLCV(
                timestamp=int(timestamp.timestamp()),
                open=float(row["open"]),
                high=float(row["high"]),
                low=float(row["low"]),
                close=float(row["close"]),
                volume=int(row["volume"]),
            )
            candles.append(ohlcv)
        
        return candles


class ChartService:
    """Service for providing chart data to frontend."""
    
    def __init__(self, feature_store, price_data_service, cache_ttl_minutes: int = 5):
        """
        Initialize chart service.
        
        Args:
            feature_store: Feature store for real-time data
            price_data_service: Service for OHLCV data
            cache_ttl_minutes: Cache TTL in minutes
        """
        self.feature_store = feature_store
        self.price_data_service = price_data_service
        self.cache = ChartDataCache(ttl_minutes=cache_ttl_minutes)
        self.active_connections: Dict[str, List[WebSocket]] = {}
        self.aggregator = OHLCVAggregator()
    
    async def get_chart_data(
        self,
        symbol: str,
        timeframe: str = "1d",
        limit: int = 100,
    ) -> Dict:
        """
        Get chart data for symbol.
        
        Args:
            symbol: IDX symbol (e.g., "BBCA.JK")
            timeframe: Timeframe (1m, 5m, 15m, 30m, 1h, 4h, 1d, 1w, 1mo)
            limit: Number of candles to return
            
        Returns:
            Dict with metadata and candles
        """
        # Validate symbol
        is_valid, error = IDXSymbolValidator.validate(symbol)
        if not is_valid:
            raise HTTPException(status_code=400, detail=error)
        
        # Check cache
        cache_key = f"{symbol}:{timeframe}:{limit}"
        cached_data = self.cache.get(cache_key)
        if cached_data:
            return cached_data
        
        try:
            # Get metadata
            metadata = IDXSymbolValidator.get_metadata(symbol)
            metadata.timeframe = TimeFrame(timeframe)
            
            # Get price data
            price_df = await self.price_data_service.get_ohlcv(
                symbol=symbol,
                limit=limit + 50,  # Get extra for resampling
            )
            
            if price_df.empty:
                raise HTTPException(
                    status_code=404,
                    detail=f"No data found for symbol: {symbol}",
                )
            
            # Resample to timeframe
            timeframe_obj = TimeFrame(timeframe)
            candles = self.aggregator.resample_to_timeframe(price_df, timeframe_obj)
            
            # Take last `limit` candles
            candles = candles[-limit:]
            
            # Format response
            response = {
                "metadata": metadata.to_dict(),
                "candles": [c.to_lightweight_charts_format() for c in candles],
                "timestamp": int(datetime.now(JAKARTA_TZ).timestamp()),
                "cached": False,
            }
            
            # Cache response
            self.cache.set(cache_key, response)
            
            return response
        
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error getting chart data for {symbol}: {str(e)}")
            raise HTTPException(status_code=500, detail=str(e))
    
    async def subscribe_to_updates(
        self,
        websocket: WebSocket,
        symbol: str,
    ) -> None:
        """
        Subscribe to real-time chart updates via WebSocket.
        
        Args:
            websocket: WebSocket connection
            symbol: IDX symbol
        """
        # Validate symbol
        is_valid, error = IDXSymbolValidator.validate(symbol)
        if not is_valid:
            await websocket.close(code=1008, reason=error)
            return
        
        # Add connection
        if symbol not in self.active_connections:
            self.active_connections[symbol] = []
        
        self.active_connections[symbol].append(websocket)
        
        try:
            await websocket.accept()
            
            # Send initial data
            data = await self.get_chart_data(symbol, timeframe="1d", limit=100)
            await websocket.send_json(data)
            
            # Keep connection alive
            while True:
                # Receive ping from client (keep-alive)
                message = await websocket.receive_text()
                
                if message == "ping":
                    await websocket.send_text("pong")
                elif message == "update":
                    # Send latest candle
                    data = await self.get_chart_data(symbol, timeframe="1d", limit=100)
                    await websocket.send_json(data)
        
        except Exception as e:
            logger.error(f"WebSocket error for {symbol}: {str(e)}")
        
        finally:
            # Remove connection
            if symbol in self.active_connections:
                self.active_connections[symbol].remove(websocket)
    
    async def broadcast_update(
        self,
        symbol: str,
        candle: OHLCV,
    ) -> None:
        """
        Broadcast new candle to all connected clients.
        
        Args:
            symbol: IDX symbol
            candle: New OHLCV candle
        """
        if symbol not in self.active_connections:
            return
        
        message = {
            "type": "candle_update",
            "symbol": symbol,
            "candle": candle.to_lightweight_charts_format(),
            "timestamp": int(datetime.now(JAKARTA_TZ).timestamp()),
        }
        
        # Send to all connected clients
        disconnected = []
        for websocket in self.active_connections[symbol]:
            try:
                await websocket.send_json(message)
            except Exception as e:
                logger.warning(f"Failed to send update: {str(e)}")
                disconnected.append(websocket)
        
        # Clean up disconnected clients
        for ws in disconnected:
            self.active_connections[symbol].remove(ws)
        
        # Invalidate cache for this symbol
        self.cache.invalidate(f"{symbol}:1d:")
    
    def is_trading_hours(self) -> bool:
        """Check if current time is within BEI trading hours."""
        now = datetime.now(JAKARTA_TZ)
        
        # Check if weekday (Monday-Friday)
        if now.weekday() >= 5:  # Saturday = 5, Sunday = 6
            return False
        
        # Check if within trading hours (09:30-16:00)
        trading_start = now.replace(hour=BEI_OPEN_HOUR, minute=BEI_OPEN_MINUTE, second=0, microsecond=0)
        trading_end = now.replace(hour=BEI_CLOSE_HOUR, minute=BEI_CLOSE_MINUTE, second=0, microsecond=0)
        
        return trading_start <= now <= trading_end
    
    def get_next_trading_time(self) -> datetime:
        """Get next trading open time."""
        now = datetime.now(JAKARTA_TZ)
        
        # If before market open today, return today's open
        today_open = now.replace(hour=BEI_OPEN_HOUR, minute=BEI_OPEN_MINUTE, second=0, microsecond=0)
        if now < today_open and now.weekday() < 5:
            return today_open
        
        # Find next trading day
        next_day = now + timedelta(days=1)
        while next_day.weekday() >= 5:  # Skip weekends
            next_day += timedelta(days=1)
        
        return next_day.replace(hour=BEI_OPEN_HOUR, minute=BEI_OPEN_MINUTE, second=0, microsecond=0)


# Global chart service instance
_chart_service: Optional[ChartService] = None


def get_chart_service() -> ChartService:
    """Get chart service instance."""
    global _chart_service
    if _chart_service is None:
        raise RuntimeError("Chart service not initialized")
    return _chart_service


def init_chart_service(feature_store, price_data_service) -> ChartService:
    """Initialize chart service."""
    global _chart_service
    _chart_service = ChartService(feature_store, price_data_service)
    return _chart_service
