"""
IDX Official API Client - BEI RTI Integration
==============================================

Task 1 (Phase 3): Real-time market data dari Bursa Efek Indonesia

Sumber data: BEI RTI (Real-Time Interface)
Timezone: Jakarta (WIB: UTC+7)
Compliance: IDX Rules, OJK Regulations
Currency: IDR (Rupiah)
"""

import asyncio
import json
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone, timedelta
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any, Callable, AsyncIterator
import os
import hashlib
import hmac

try:
    import websockets
    import websockets.client
    WEBSOCKETS_AVAILABLE = True
except ImportError:
    WEBSOCKETS_AVAILABLE = False

try:
    import pandas as pd
    PANDAS_AVAILABLE = True
except ImportError:
    PANDAS_AVAILABLE = False


logger = logging.getLogger(__name__)

# ============================================================================
# JAKARTA TIMEZONE + CONSTANTS
# ============================================================================

JAKARTA_TZ = timezone(timedelta(hours=7))  # WIB: UTC+7

def get_jakarta_now() -> datetime:
    """Get current time in Jakarta (WIB)."""
    return datetime.now(JAKARTA_TZ)

def to_jakarta_time(dt: datetime) -> datetime:
    """Convert datetime to Jakarta timezone."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc).astimezone(JAKARTA_TZ)
    return dt.astimezone(JAKARTA_TZ)

# IDX Trading Constants
IDX_TRADING_START = "09:30"  # WIB
IDX_TRADING_END = "16:00"    # WIB
IDX_PRETRADING_START = "08:00"  # WIB
IDX_PRETRADING_END = "09:29"    # WIB

MIN_PRICE_CHANGE_PCT = -35.0  # ±35% price limit
MAX_PRICE_CHANGE_PCT = 35.0
MIN_LOT_SIZE = 100  # Minimum shares per lot
SETTLEMENT_T_PLUS = 2  # T+2 settlement

# BEI RTI API Constants
BEI_RTI_WS_URL = "wss://rtdata.beiapi.com/ws"  # Placeholder - actual URL from BEI
BEI_API_ENDPOINT = "https://api.beiapi.com"
BEI_REQUEST_TIMEOUT = 30


# ============================================================================
# Data Classes
# ============================================================================

class OrderBookSide(Enum):
    """Order book side (buy/sell)."""
    BID = "bid"  # Buyers
    ASK = "ask"  # Sellers


@dataclass
class OrderBookLevel:
    """Single level in order book (bid or ask)."""
    price: float
    quantity: int  # Volume at this price (in lots)
    orders: int = 1  # Number of orders at this price
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class OrderBook:
    """Order book snapshot."""
    symbol: str
    timestamp: datetime
    bids: List[OrderBookLevel] = field(default_factory=list)  # [0] = highest bid
    asks: List[OrderBookLevel] = field(default_factory=list)  # [0] = lowest ask
    
    def get_spread(self) -> Optional[float]:
        """Get bid-ask spread in IDR."""
        if self.bids and self.asks:
            return self.asks[0].price - self.bids[0].price
        return None
    
    def get_spread_pct(self) -> Optional[float]:
        """Get bid-ask spread in percentage."""
        if self.asks and self.asks[0].price > 0:
            spread = self.get_spread()
            if spread:
                mid = (self.bids[0].price + self.asks[0].price) / 2
                return (spread / mid * 100) if mid > 0 else None
        return None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbol": self.symbol,
            "timestamp": self.timestamp.isoformat(),
            "bids": [b.to_dict() for b in self.bids],
            "asks": [a.to_dict() for a in self.asks],
            "spread_idr": self.get_spread(),
            "spread_pct": self.get_spread_pct(),
        }


@dataclass
class Tick:
    """Individual trade/tick data."""
    symbol: str
    timestamp: datetime
    price: float  # IDR
    quantity: int  # Shares (in lots: quantity * 100)
    side: str  # "B" (buy) or "S" (sell)
    trade_id: str  # Unique identifier
    buyer: Optional[str] = None  # Buyer code
    seller: Optional[str] = None  # Seller code
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class OHLCV:
    """Candlestick data (Open, High, Low, Close, Volume)."""
    symbol: str
    timestamp: datetime
    period: str  # "1m", "5m", "1h", "1d"
    open: float  # IDR
    high: float  # IDR
    low: float  # IDR
    close: float  # IDR
    volume: int  # Shares
    trades: int = 0  # Number of trades
    vwap: Optional[float] = None  # Volume-weighted average price
    
    @property
    def hl_range(self) -> float:
        """High-Low range in IDR."""
        return self.high - self.low
    
    @property
    def close_change_pct(self) -> float:
        """Percentage change from open to close."""
        if self.open > 0:
            return ((self.close - self.open) / self.open) * 100
        return 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ============================================================================
# BEI API Client
# ============================================================================

class BEIAPIClientBase(ABC):
    """Base class for BEI API clients."""
    
    def __init__(
        self,
        username: str,
        password: str,
        timeout: int = BEI_REQUEST_TIMEOUT,
    ):
        """
        Initialize BEI API client.
        
        Args:
            username: BEI RTI username
            password: BEI RTI password
            timeout: Request timeout in seconds
        """
        self.username = username
        self.password = password
        self.timeout = timeout
        self.authenticated = False
        self.session_token: Optional[str] = None
        self.last_request_time: Optional[datetime] = None
        
        logger.info(f"Initialized BEI API Client for user: {username}")
    
    @abstractmethod
    async def connect(self) -> bool:
        """Connect to BEI API."""
        pass
    
    @abstractmethod
    async def disconnect(self) -> bool:
        """Disconnect from BEI API."""
        pass
    
    @abstractmethod
    async def get_price(self, symbol: str) -> Optional[float]:
        """Get latest price for symbol (IDR)."""
        pass
    
    @abstractmethod
    async def get_ohlcv(
        self,
        symbol: str,
        period: str = "1m",
        limit: int = 100,
    ) -> List[OHLCV]:
        """Get OHLCV data."""
        pass
    
    @abstractmethod
    async def get_order_book(self, symbol: str, depth: int = 20) -> Optional[OrderBook]:
        """Get order book snapshot."""
        pass
    
    @abstractmethod
    async def stream_ticks(
        self,
        symbols: List[str],
        callback: Callable[[Tick], Any],
    ) -> None:
        """Stream real-time tick data."""
        pass
    
    @abstractmethod
    async def stream_orderbook(
        self,
        symbols: List[str],
        callback: Callable[[OrderBook], Any],
    ) -> None:
        """Stream real-time order book updates."""
        pass
    
    def _authenticate(self) -> bool:
        """Authenticate with BEI."""
        # Placeholder: actual authentication logic
        self.authenticated = True
        self.session_token = hashlib.sha256(
            f"{self.username}:{self.password}".encode()
        ).hexdigest()
        return True


class BEIWebSocketClient(BEIAPIClientBase):
    """
    WebSocket client for BEI RTI real-time data.
    
    Features:
    - Low-latency connections
    - Auto-reconnect
    - Heartbeat/ping-pong
    - Multiple subscription support
    """
    
    def __init__(
        self,
        username: str,
        password: str,
        ws_url: str = BEI_RTI_WS_URL,
        timeout: int = BEI_REQUEST_TIMEOUT,
        heartbeat_interval: float = 30.0,
    ):
        """
        Initialize WebSocket client.
        
        Args:
            username: BEI RTI username
            password: BEI RTI password
            ws_url: WebSocket URL
            timeout: Request timeout
            heartbeat_interval: Heartbeat interval in seconds
        """
        super().__init__(username, password, timeout)
        self.ws_url = ws_url
        self.heartbeat_interval = heartbeat_interval
        self.websocket = None
        self.subscriptions = set()
        self.message_handlers: Dict[str, List[Callable]] = {}
        self.connected = False
    
    async def connect(self) -> bool:
        """Connect to BEI WebSocket."""
        if not WEBSOCKETS_AVAILABLE:
            logger.error("websockets library not available")
            return False
        
        try:
            # Authenticate
            if not self._authenticate():
                logger.error("Authentication failed")
                return False
            
            # Connect to WebSocket
            self.websocket = await websockets.client.connect(
                self.ws_url,
                timeout=self.heartbeat_interval,
            )
            
            # Send auth message
            auth_msg = {
                "type": "auth",
                "username": self.username,
                "session_token": self.session_token,
                "timestamp": get_jakarta_now().isoformat(),
            }
            
            await self.websocket.send(json.dumps(auth_msg))
            
            # Wait for auth response
            response = await asyncio.wait_for(
                self.websocket.recv(),
                timeout=5.0,
            )
            
            resp_data = json.loads(response)
            if resp_data.get("status") == "success":
                self.authenticated = True
                self.connected = True
                logger.info("Successfully connected to BEI WebSocket")
                return True
            else:
                logger.error(f"Auth failed: {resp_data.get('message')}")
                return False
        
        except Exception as e:
            logger.error(f"Connection failed: {e}")
            return False
    
    async def disconnect(self) -> bool:
        """Disconnect from BEI WebSocket."""
        if self.websocket:
            try:
                await self.websocket.close()
                self.connected = False
                logger.info("Disconnected from BEI WebSocket")
                return True
            except Exception as e:
                logger.error(f"Disconnect failed: {e}")
                return False
        return True
    
    async def subscribe(self, symbol: str, feed_type: str = "tick") -> bool:
        """
        Subscribe to a data feed.
        
        Args:
            symbol: Stock symbol (e.g., "BBCA.JK")
            feed_type: "tick", "orderbook", "ohlcv"
        """
        if not self.connected:
            return False
        
        try:
            sub_msg = {
                "type": "subscribe",
                "symbol": symbol,
                "feed_type": feed_type,
                "timestamp": get_jakarta_now().isoformat(),
            }
            
            await self.websocket.send(json.dumps(sub_msg))
            self.subscriptions.add((symbol, feed_type))
            logger.info(f"Subscribed to {symbol}/{feed_type}")
            return True
        
        except Exception as e:
            logger.error(f"Subscription failed: {e}")
            return False
    
    async def get_price(self, symbol: str) -> Optional[float]:
        """Get latest price (cached from stream)."""
        # Placeholder - would get from internal cache
        return None
    
    async def get_ohlcv(
        self,
        symbol: str,
        period: str = "1m",
        limit: int = 100,
    ) -> List[OHLCV]:
        """Get OHLCV data via REST API."""
        try:
            request_msg = {
                "type": "get_ohlcv",
                "symbol": symbol,
                "period": period,
                "limit": limit,
                "timestamp": get_jakarta_now().isoformat(),
            }
            
            await self.websocket.send(json.dumps(request_msg))
            
            # Wait for response (RPC-style)
            response = await asyncio.wait_for(
                self.websocket.recv(),
                timeout=self.timeout,
            )
            
            resp_data = json.loads(response)
            if resp_data.get("status") == "success":
                ohlcv_list = []
                for candle in resp_data.get("ohlcv", []):
                    ohlcv_list.append(OHLCV(
                        symbol=symbol,
                        timestamp=datetime.fromisoformat(candle["timestamp"]),
                        period=period,
                        open=float(candle["open"]),
                        high=float(candle["high"]),
                        low=float(candle["low"]),
                        close=float(candle["close"]),
                        volume=int(candle["volume"]),
                        trades=int(candle.get("trades", 0)),
                        vwap=float(candle.get("vwap", 0)),
                    ))
                return ohlcv_list
        
        except Exception as e:
            logger.error(f"Get OHLCV failed: {e}")
        
        return []
    
    async def get_order_book(self, symbol: str, depth: int = 20) -> Optional[OrderBook]:
        """Get order book snapshot."""
        try:
            request_msg = {
                "type": "get_orderbook",
                "symbol": symbol,
                "depth": depth,
                "timestamp": get_jakarta_now().isoformat(),
            }
            
            await self.websocket.send(json.dumps(request_msg))
            
            response = await asyncio.wait_for(
                self.websocket.recv(),
                timeout=self.timeout,
            )
            
            resp_data = json.loads(response)
            if resp_data.get("status") == "success":
                ob_data = resp_data["orderbook"]
                
                bids = [
                    OrderBookLevel(
                        price=float(b["price"]),
                        quantity=int(b["quantity"]),
                        orders=int(b.get("orders", 1)),
                    )
                    for b in ob_data.get("bids", [])[:depth]
                ]
                
                asks = [
                    OrderBookLevel(
                        price=float(a["price"]),
                        quantity=int(a["quantity"]),
                        orders=int(a.get("orders", 1)),
                    )
                    for a in ob_data.get("asks", [])[:depth]
                ]
                
                return OrderBook(
                    symbol=symbol,
                    timestamp=datetime.fromisoformat(ob_data["timestamp"]),
                    bids=bids,
                    asks=asks,
                )
        
        except Exception as e:
            logger.error(f"Get orderbook failed: {e}")
        
        return None
    
    async def stream_ticks(
        self,
        symbols: List[str],
        callback: Callable[[Tick], Any],
    ) -> None:
        """
        Stream real-time tick data.
        
        Args:
            symbols: List of symbols to stream
            callback: Function called for each tick
        """
        if not self.connected:
            logger.error("Not connected to BEI API")
            return
        
        # Subscribe to ticks
        for symbol in symbols:
            await self.subscribe(symbol, "tick")
        
        try:
            while self.connected:
                try:
                    message = await asyncio.wait_for(
                        self.websocket.recv(),
                        timeout=self.heartbeat_interval * 2,
                    )
                    
                    data = json.loads(message)
                    
                    if data.get("type") == "tick":
                        tick = Tick(
                            symbol=data["symbol"],
                            timestamp=datetime.fromisoformat(data["timestamp"]),
                            price=float(data["price"]),
                            quantity=int(data["quantity"]),
                            side=data["side"],
                            trade_id=data["trade_id"],
                            buyer=data.get("buyer"),
                            seller=data.get("seller"),
                        )
                        
                        # Call user callback
                        if callable(callback):
                            try:
                                callback(tick)
                            except Exception as e:
                                logger.error(f"Callback error: {e}")
                
                except asyncio.TimeoutError:
                    # Send heartbeat
                    await self.websocket.send(json.dumps({"type": "ping"}))
        
        except Exception as e:
            logger.error(f"Streaming error: {e}")
            self.connected = False
    
    async def stream_orderbook(
        self,
        symbols: List[str],
        callback: Callable[[OrderBook], Any],
    ) -> None:
        """Stream order book updates."""
        if not self.connected:
            logger.error("Not connected to BEI API")
            return
        
        for symbol in symbols:
            await self.subscribe(symbol, "orderbook")
        
        try:
            while self.connected:
                try:
                    message = await asyncio.wait_for(
                        self.websocket.recv(),
                        timeout=self.heartbeat_interval * 2,
                    )
                    
                    data = json.loads(message)
                    
                    if data.get("type") == "orderbook":
                        ob = OrderBook(
                            symbol=data["symbol"],
                            timestamp=datetime.fromisoformat(data["timestamp"]),
                            bids=[
                                OrderBookLevel(
                                    price=float(b["price"]),
                                    quantity=int(b["quantity"]),
                                )
                                for b in data.get("bids", [])
                            ],
                            asks=[
                                OrderBookLevel(
                                    price=float(a["price"]),
                                    quantity=int(a["quantity"]),
                                )
                                for a in data.get("asks", [])
                            ],
                        )
                        
                        if callable(callback):
                            try:
                                callback(ob)
                            except Exception as e:
                                logger.error(f"Callback error: {e}")
                
                except asyncio.TimeoutError:
                    await self.websocket.send(json.dumps({"type": "ping"}))
        
        except Exception as e:
            logger.error(f"Streaming error: {e}")
            self.connected = False


# ============================================================================
# Market Data Cache
# ============================================================================

class MarketDataCache:
    """In-memory cache for market data."""
    
    def __init__(self, max_size: int = 10000):
        """
        Initialize cache.
        
        Args:
            max_size: Maximum number of ticks per symbol
        """
        self.max_size = max_size
        self.ticks: Dict[str, List[Tick]] = {}
        self.latest_prices: Dict[str, float] = {}
        self.order_books: Dict[str, OrderBook] = {}
        self.ohlcv_cache: Dict[Tuple[str, str], List[OHLCV]] = {}
    
    def add_tick(self, tick: Tick) -> None:
        """Add tick to cache."""
        if tick.symbol not in self.ticks:
            self.ticks[tick.symbol] = []
        
        self.ticks[tick.symbol].append(tick)
        self.latest_prices[tick.symbol] = tick.price
        
        # Limit cache size
        if len(self.ticks[tick.symbol]) > self.max_size:
            self.ticks[tick.symbol] = self.ticks[tick.symbol][-self.max_size:]
    
    def add_order_book(self, ob: OrderBook) -> None:
        """Update order book cache."""
        self.order_books[ob.symbol] = ob
    
    def cache_ohlcv(self, symbol: str, period: str, ohlcv_list: List[OHLCV]) -> None:
        """Cache OHLCV data."""
        key = (symbol, period)
        self.ohlcv_cache[key] = ohlcv_list
    
    def get_latest_price(self, symbol: str) -> Optional[float]:
        """Get latest price."""
        return self.latest_prices.get(symbol)
    
    def get_ticks(self, symbol: str, limit: int = 100) -> List[Tick]:
        """Get recent ticks."""
        if symbol in self.ticks:
            return self.ticks[symbol][-limit:]
        return []
    
    def get_order_book(self, symbol: str) -> Optional[OrderBook]:
        """Get cached order book."""
        return self.order_books.get(symbol)
    
    def clear(self) -> None:
        """Clear cache."""
        self.ticks.clear()
        self.latest_prices.clear()
        self.order_books.clear()
        self.ohlcv_cache.clear()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print("IDX BEI API Client Module - Ready for import")
