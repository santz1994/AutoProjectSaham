"""TradingView chart service for real-time OHLCV data.

Provides API primitives for lightweight-charts integration with:
- real-time websocket streaming (OHLCV)
- Jakarta timezone (WIB: UTC+7) support
- Forex/Crypto symbol validation and metadata
- market-aware trading status (Forex 24x5, Crypto 24x7)
- in-memory caching for performance
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, asdict
from enum import Enum

import pytz
import pandas as pd
from fastapi import WebSocket, HTTPException

# Initialize Jakarta timezone
JAKARTA_TZ = pytz.timezone("Asia/Jakarta")
FOREX_LAST_TRADING_WEEKDAY = 4  # Friday

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
    symbol: str
    exchange: str
    currency: str
    timeframe: TimeFrame
    description: str
    decimal_places: int
    min_lot_size: float
    trading_start: str
    trading_end: str
    timezone: str
    
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


class MarketSymbolValidator:
    """Validate Forex/Crypto symbol format and properties."""

    SYMBOLS = {
        "EURUSD=X": {
            "name": "EUR/USD",
            "sector": "Forex",
            "decimal_places": 5,
            "min_lot_size": 0.01,
            "min_price": 0.5,
            "max_price": 2.0,
        },
        "GBPUSD=X": {
            "name": "GBP/USD",
            "sector": "Forex",
            "decimal_places": 5,
            "min_lot_size": 0.01,
            "min_price": 0.5,
            "max_price": 2.0,
        },
        "USDJPY=X": {
            "name": "USD/JPY",
            "sector": "Forex",
            "decimal_places": 3,
            "min_lot_size": 0.01,
            "min_price": 50.0,
            "max_price": 250.0,
        },
        "BTC-USD": {
            "name": "Bitcoin / US Dollar",
            "sector": "Crypto",
            "decimal_places": 2,
            "min_lot_size": 0.001,
            "min_price": 5000,
            "max_price": 1000000,
        },
        "ETH-USD": {
            "name": "Ethereum / US Dollar",
            "sector": "Crypto",
            "decimal_places": 2,
            "min_lot_size": 0.001,
            "min_price": 100,
            "max_price": 100000,
        },
        "SOL-USD": {
            "name": "Solana / US Dollar",
            "sector": "Crypto",
            "decimal_places": 2,
            "min_lot_size": 0.001,
            "min_price": 1,
            "max_price": 10000,
        },
    }

    # Backward compatibility for modules still importing IDX_SYMBOLS.
    IDX_SYMBOLS = SYMBOLS

    @staticmethod
    def _normalize(symbol: str) -> str:
        return str(symbol or "").strip().upper()

    @staticmethod
    def _is_forex_symbol(normalized: str) -> bool:
        if normalized.endswith("=X"):
            pair = normalized[:-2]
            return len(pair) == 6 and pair.isalpha()

        if "/" in normalized:
            parts = normalized.split("/", 1)
            if len(parts) != 2:
                return False
            base, quote = parts
            compact = f"{base}{quote}"
            return len(base) == 3 and len(quote) == 3 and compact.isalpha()

        return len(normalized) == 6 and normalized.isalpha()

    @staticmethod
    def _is_crypto_symbol(normalized: str) -> bool:
        if "-USD" in normalized:
            base = normalized.split("-USD", 1)[0]
            return bool(base) and base.isalnum()

        if normalized.endswith("USDT") and len(normalized) > 4:
            base = normalized[:-4]
            return bool(base) and base.isalnum()

        if "/" in normalized:
            parts = normalized.split("/", 1)
            if len(parts) != 2:
                return False
            base, quote = parts
            return base.isalnum() and quote in {"USD", "USDT", "USDC"}

        return False

    @staticmethod
    def detect_market(symbol: str) -> Optional[str]:
        """Return market type for a symbol: forex, crypto, or None."""
        normalized = MarketSymbolValidator._normalize(symbol)
        if not normalized:
            return None

        if MarketSymbolValidator._is_forex_symbol(normalized):
            return "forex"

        if MarketSymbolValidator._is_crypto_symbol(normalized):
            return "crypto"

        return None

    @staticmethod
    def _quote_currency(normalized: str, market: str) -> str:
        if market == "forex":
            pair = normalized
            if pair.endswith("=X"):
                pair = pair[:-2]
            pair = pair.replace("/", "")
            if len(pair) == 6 and pair.isalpha():
                return pair[3:]
            return "USD"

        if normalized.endswith("USDT") or normalized.endswith("/USDT"):
            return "USDT"

        if normalized.endswith("USDC") or normalized.endswith("/USDC"):
            return "USDC"

        return "USD"

    @staticmethod
    def _default_decimal_places(normalized: str, market: str) -> int:
        if market == "forex":
            pair = (
                normalized[:-2]
                if normalized.endswith("=X")
                else normalized.replace("/", "")
            )
            if pair.endswith("JPY"):
                return 3
            return 5

        return 2
    
    @staticmethod
    def validate(symbol: str) -> Tuple[bool, Optional[str]]:
        """
        Validate Forex/Crypto symbol format.
        
        Args:
            symbol: Symbol to validate (e.g., "EURUSD=X", "BTC-USD")
            
        Returns:
            Tuple of (is_valid, error_message)
        """
        if not isinstance(symbol, str):
            return False, "Symbol must be string"

        market = MarketSymbolValidator.detect_market(symbol)
        if market is None:
            return False, (
                "Only Forex/Crypto symbols are supported. "
                "Examples: EURUSD=X, BTC-USD"
            )
        
        return True, None
    
    @staticmethod
    def get_metadata(symbol: str) -> ChartMetadata:
        """Get metadata for symbol."""
        normalized_symbol = MarketSymbolValidator._normalize(symbol)

        is_valid, error = MarketSymbolValidator.validate(normalized_symbol)
        if not is_valid:
            raise ValueError(f"Invalid symbol: {error}")

        market = MarketSymbolValidator.detect_market(normalized_symbol) or "forex"

        symbol_info = MarketSymbolValidator.SYMBOLS.get(normalized_symbol, {
            "name": normalized_symbol,
            "sector": "Unknown",
            "decimal_places": MarketSymbolValidator._default_decimal_places(
                normalized_symbol,
                market,
            ),
            "min_lot_size": 0.01 if market == "forex" else 0.001,
        })

        return ChartMetadata(
            symbol=normalized_symbol,
            exchange="FOREX" if market == "forex" else "CRYPTO",
            currency=MarketSymbolValidator._quote_currency(normalized_symbol, market),
            timeframe=TimeFrame.D1,
            description=symbol_info.get("name", normalized_symbol),
            decimal_places=int(symbol_info.get("decimal_places", 5)),
            min_lot_size=float(symbol_info.get("min_lot_size", 0.01)),
            trading_start="00:00",
            trading_end="23:59",
            timezone="Asia/Jakarta",
        )


class IDXSymbolValidator(MarketSymbolValidator):
    """Backward-compatible alias for modules importing IDXSymbolValidator."""


class ChartDataCache:
    """In-memory cache for chart data."""
    
    def __init__(self, ttl_minutes: int = 5):
        """
        Initialize cache.
        
        Args:
            ttl_minutes: Time-to-live for cache entries (default 5 minutes)
        """
        self.cache: Dict[str, Tuple[Dict, datetime]] = {}
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

    def invalidate_prefix(self, prefix: str) -> None:
        """Invalidate all cache entries that start with the provided prefix."""
        keys_to_remove = [key for key in self.cache if key.startswith(prefix)]
        for key in keys_to_remove:
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
            TimeFrame.D1: "1D",
            TimeFrame.W1: "1W",
            TimeFrame.MN1: "1ME",
        }
        
        freq = freq_map.get(timeframe, "1D")
        
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
            symbol: Forex/Crypto symbol (e.g., "EURUSD=X", "BTC-USD")
            timeframe: Timeframe (1m, 5m, 15m, 30m, 1h, 4h, 1d, 1w, 1mo)
            limit: Number of candles to return
            
        Returns:
            Dict with metadata and candles
        """
        normalized_symbol = str(symbol or "").strip().upper()

        # Validate symbol
        is_valid, error = MarketSymbolValidator.validate(normalized_symbol)
        if not is_valid:
            raise HTTPException(status_code=400, detail=error)

        try:
            timeframe_obj = TimeFrame(timeframe)
        except ValueError as exc:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Invalid timeframe: {timeframe}. "
                    "Valid values: 1m, 5m, 15m, 30m, 1h, 4h, 1d, 1w, 1mo"
                ),
            ) from exc
        
        # Check cache
        cache_key = f"{normalized_symbol}:{timeframe}:{limit}"
        cached_data = self.cache.get(cache_key)
        if cached_data:
            return cached_data
        
        try:
            # Get metadata
            metadata = MarketSymbolValidator.get_metadata(normalized_symbol)
            metadata.timeframe = timeframe_obj
            
            # Get price data
            price_df = await self.price_data_service.get_ohlcv(
                symbol=normalized_symbol,
                limit=limit + 50,  # Get extra for resampling
            )
            
            if price_df.empty:
                raise HTTPException(
                    status_code=404,
                    detail=f"No data found for symbol: {normalized_symbol}",
                )
            
            # Resample to timeframe
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
            logger.error(f"Error getting chart data for {normalized_symbol}: {str(e)}")
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
            symbol: Forex/Crypto symbol
        """
        normalized_symbol = str(symbol or "").strip().upper()

        # Validate symbol
        is_valid, error = MarketSymbolValidator.validate(normalized_symbol)
        if not is_valid:
            await websocket.close(code=1008, reason=error)
            return
        
        # Add connection
        if normalized_symbol not in self.active_connections:
            self.active_connections[normalized_symbol] = []
        
        self.active_connections[normalized_symbol].append(websocket)
        
        try:
            await websocket.accept()
            
            # Send initial data
            data = await self.get_chart_data(normalized_symbol, timeframe="1d", limit=100)
            await websocket.send_json(data)
            
            # Keep connection alive
            while True:
                # Receive ping from client (keep-alive)
                message = await websocket.receive_text()
                
                if message == "ping":
                    await websocket.send_text("pong")
                elif message == "update":
                    # Send latest candle
                    data = await self.get_chart_data(normalized_symbol, timeframe="1d", limit=100)
                    await websocket.send_json(data)
        
        except Exception as e:
            logger.error(f"WebSocket error for {normalized_symbol}: {str(e)}")
        
        finally:
            # Remove connection
            if normalized_symbol in self.active_connections and websocket in self.active_connections[normalized_symbol]:
                self.active_connections[normalized_symbol].remove(websocket)
    
    async def broadcast_update(
        self,
        symbol: str,
        candle: OHLCV,
    ) -> None:
        """
        Broadcast new candle to all connected clients.
        
        Args:
            symbol: Forex/Crypto symbol
            candle: New OHLCV candle
        """
        normalized_symbol = str(symbol or "").strip().upper()

        if normalized_symbol not in self.active_connections:
            return
        
        message = {
            "type": "candle_update",
            "symbol": normalized_symbol,
            "candle": candle.to_lightweight_charts_format(),
            "timestamp": int(datetime.now(JAKARTA_TZ).timestamp()),
        }
        
        # Send to all connected clients
        disconnected = []
        for websocket in self.active_connections[normalized_symbol]:
            try:
                await websocket.send_json(message)
            except Exception as e:
                logger.warning(f"Failed to send update: {str(e)}")
                disconnected.append(websocket)
        
        # Clean up disconnected clients
        for ws in disconnected:
            self.active_connections[normalized_symbol].remove(ws)
        
        # Invalidate cache for this symbol
        self.cache.invalidate_prefix(f"{normalized_symbol}:")
    
    def is_trading_hours(self, symbol: Optional[str] = None) -> bool:
        """Check if current time is within market trading hours."""
        market = MarketSymbolValidator.detect_market(symbol or "") if symbol else "forex"
        if market == "crypto":
            return True

        now = datetime.now(JAKARTA_TZ)
        return now.weekday() <= FOREX_LAST_TRADING_WEEKDAY
    
    def get_next_trading_time(self, symbol: Optional[str] = None) -> datetime:
        """Get next trading open time for market."""
        market = MarketSymbolValidator.detect_market(symbol or "") if symbol else "forex"
        now = datetime.now(JAKARTA_TZ)

        if market == "crypto":
            return now

        if self.is_trading_hours(symbol):
            return now

        next_day = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        while next_day.weekday() > FOREX_LAST_TRADING_WEEKDAY:
            next_day += timedelta(days=1)

        return next_day


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
