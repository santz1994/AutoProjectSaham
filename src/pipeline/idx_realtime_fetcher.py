"""
IDX Real-time Data Fetcher
===========================

Task 1 (Phase 3): Event-driven real-time data streaming

Features:
- Async/await based streaming
- Connection pooling and resilience
- Fallback mechanisms
- Auto-reconnect with exponential backoff
- Buffer management
- Health monitoring
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Dict, List, Optional, Set, Callable, Any
from collections import deque

from .idx_api_client import (
    BEIWebSocketClient, BEIAPIClientBase, Tick, OrderBook, OHLCV,
    get_jakarta_now, to_jakarta_time, JAKARTA_TZ,
)
from .idx_market_data import IDXMarketDataManager, SymbolInfo


logger = logging.getLogger(__name__)


# ============================================================================
# Enums & Constants
# ============================================================================

class ConnectionState(Enum):
    """Connection state."""
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    RECONNECTING = "reconnecting"
    ERROR = "error"


class StreamType(Enum):
    """Type of data stream."""
    TICK = "tick"
    ORDERBOOK = "orderbook"
    OHLCV = "ohlcv"


# ============================================================================
# Data Classes
# ============================================================================

@dataclass
class StreamConfig:
    """Configuration for data streaming."""
    # Connection
    ws_url: str = "wss://rtdata.beiapi.com/ws"
    max_reconnect_attempts: int = 10
    reconnect_initial_delay: float = 1.0  # seconds
    reconnect_max_delay: float = 60.0  # seconds
    reconnect_backoff: float = 1.5
    
    # Buffering
    buffer_size: int = 10000  # Max ticks in buffer
    buffer_flush_interval: float = 1.0  # seconds
    
    # Health monitoring
    heartbeat_interval: float = 30.0  # seconds
    heartbeat_timeout: float = 60.0  # seconds
    
    # Symbols to stream
    symbols: List[str] = field(default_factory=list)
    orderbook_depth: int = 20
    
    # Callbacks
    on_tick: Optional[Callable[[Tick], None]] = None
    on_orderbook: Optional[Callable[[OrderBook], None]] = None
    on_ohlcv: Optional[Callable[[OHLCV], None]] = None
    on_connection_lost: Optional[Callable[[], None]] = None


@dataclass
class ConnectionHealth:
    """Health metrics for connection."""
    state: ConnectionState = ConnectionState.DISCONNECTED
    connected_at: Optional[datetime] = None
    uptime_seconds: float = 0.0
    
    ticks_received: int = 0
    ticks_buffered: int = 0
    ticks_processed: int = 0
    
    errors: int = 0
    reconnects: int = 0
    last_error: Optional[str] = None
    last_error_at: Optional[datetime] = None
    
    def get_uptime(self) -> timedelta:
        """Get connection uptime."""
        if self.connected_at:
            return get_jakarta_now() - self.connected_at
        return timedelta(0)


# ============================================================================
# Real-time Data Fetcher
# ============================================================================

class IDXRealtimeFetcher:
    """
    Fetches real-time market data from BEI API.
    
    Responsibilities:
    - Maintain persistent WebSocket connection
    - Subscribe to symbols
    - Buffer incoming data
    - Forward to market data manager
    - Handle reconnections and errors
    - Monitor connection health
    """
    
    def __init__(
        self,
        api_client: BEIWebSocketClient,
        market_data_mgr: IDXMarketDataManager,
        config: Optional[StreamConfig] = None,
    ):
        """
        Initialize fetcher.
        
        Args:
            api_client: BEI API client
            market_data_mgr: Market data manager
            config: Stream configuration
        """
        self.api_client = api_client
        self.market_data_mgr = market_data_mgr
        self.config = config or StreamConfig()
        
        # State
        self.health = ConnectionHealth()
        self.running = False
        self.tick_buffer: deque = deque(maxlen=self.config.buffer_size)
        self.subscribed_symbols: Set[str] = set()
        
        # Tasks
        self.stream_task: Optional[asyncio.Task] = None
        self.buffer_flush_task: Optional[asyncio.Task] = None
        self.health_monitor_task: Optional[asyncio.Task] = None
        
        # Reconnection
        self.reconnect_delay = self.config.reconnect_initial_delay
        self.reconnect_attempts = 0
        
        logger.info("Initialized IDXRealtimeFetcher")
    
    async def start(self) -> bool:
        """Start streaming."""
        if self.running:
            logger.warning("Fetcher already running")
            return False
        
        self.running = True
        self.health.state = ConnectionState.CONNECTING
        
        # Start background tasks
        self.buffer_flush_task = asyncio.create_task(self._buffer_flush_loop())
        self.health_monitor_task = asyncio.create_task(self._health_monitor_loop())
        
        # Connect and stream
        await self._connect_and_stream()
        
        return True
    
    async def stop(self) -> bool:
        """Stop streaming."""
        if not self.running:
            return False
        
        self.running = False
        
        # Cancel tasks
        if self.stream_task:
            self.stream_task.cancel()
        if self.buffer_flush_task:
            self.buffer_flush_task.cancel()
        if self.health_monitor_task:
            self.health_monitor_task.cancel()
        
        # Disconnect
        await self.api_client.disconnect()
        self.health.state = ConnectionState.DISCONNECTED
        
        logger.info("Fetcher stopped")
        return True
    
    async def subscribe(self, symbols: List[str]) -> bool:
        """Subscribe to symbols."""
        if not self.health.state == ConnectionState.CONNECTED:
            logger.warning("Not connected, buffering subscription")
            return False
        
        for symbol in symbols:
            if symbol not in self.subscribed_symbols:
                success = await self.api_client.subscribe(symbol, "tick")
                if success:
                    self.subscribed_symbols.add(symbol)
                    logger.info(f"Subscribed to {symbol}")
                else:
                    logger.error(f"Failed to subscribe to {symbol}")
        
        return True
    
    async def unsubscribe(self, symbols: List[str]) -> bool:
        """Unsubscribe from symbols."""
        for symbol in symbols:
            if symbol in self.subscribed_symbols:
                self.subscribed_symbols.discard(symbol)
                logger.info(f"Unsubscribed from {symbol}")
        
        return True
    
    async def _connect_and_stream(self) -> None:
        """Connect to API and stream data."""
        while self.running:
            try:
                # Connect
                self.health.state = ConnectionState.CONNECTING
                
                connected = await self.api_client.connect()
                if not connected:
                    self.health.errors += 1
                    self.health.last_error = "Connection failed"
                    self.health.last_error_at = get_jakarta_now()
                    await self._handle_reconnect()
                    continue
                
                # Reset reconnect state
                self.health.state = ConnectionState.CONNECTED
                self.health.connected_at = get_jakarta_now()
                self.reconnect_delay = self.config.reconnect_initial_delay
                self.reconnect_attempts = 0
                
                logger.info("Connected to BEI RTI API")
                
                # Subscribe to symbols
                await self.subscribe(list(self.config.symbols))
                
                # Start streaming
                self.stream_task = asyncio.create_task(
                    self._tick_stream_loop()
                )
                
                await self.stream_task
            
            except asyncio.CancelledError:
                break
            
            except Exception as e:
                logger.error(f"Streaming error: {e}")
                self.health.errors += 1
                self.health.last_error = str(e)
                self.health.last_error_at = get_jakarta_now()
                self.health.state = ConnectionState.ERROR
                
                if self.running:
                    await self._handle_reconnect()
    
    async def _tick_stream_loop(self) -> None:
        """Stream tick data."""
        def tick_callback(tick: Tick) -> None:
            """Process incoming tick."""
            self.health.ticks_received += 1
            self.tick_buffer.append(tick)
            self.health.ticks_buffered = len(self.tick_buffer)
            
            # Forward to market data manager
            self.market_data_mgr.on_tick_received(tick)
            
            # Call user callback
            if self.config.on_tick:
                try:
                    self.config.on_tick(tick)
                except Exception as e:
                    logger.error(f"Tick callback error: {e}")
        
        try:
            await self.api_client.stream_ticks(
                list(self.config.symbols),
                tick_callback,
            )
        
        except asyncio.CancelledError:
            raise
        
        except Exception as e:
            logger.error(f"Tick stream error: {e}")
            self.health.state = ConnectionState.RECONNECTING
            if self.running:
                await self._handle_reconnect()
    
    async def _buffer_flush_loop(self) -> None:
        """Periodically flush buffer."""
        while self.running:
            try:
                await asyncio.sleep(self.config.buffer_flush_interval)
                
                # Process buffered ticks
                while self.tick_buffer:
                    try:
                        tick = self.tick_buffer.popleft()
                        # Tick already processed in callback
                        self.health.ticks_processed += 1
                    except Exception as e:
                        logger.error(f"Buffer flush error: {e}")
            
            except asyncio.CancelledError:
                break
            
            except Exception as e:
                logger.error(f"Buffer flush loop error: {e}")
    
    async def _health_monitor_loop(self) -> None:
        """Monitor connection health."""
        while self.running:
            try:
                await asyncio.sleep(self.config.heartbeat_interval)
                
                # Update uptime
                if self.health.connected_at:
                    self.health.uptime_seconds = (
                        get_jakarta_now() - self.health.connected_at
                    ).total_seconds()
                
                # Check if connected
                if self.health.state == ConnectionState.CONNECTED:
                    # Check last tick received (basic health check)
                    # Could add timeout logic here
                    pass
                
                logger.debug(
                    f"Health: {self.health.state.value}, "
                    f"Ticks: {self.health.ticks_received}, "
                    f"Errors: {self.health.errors}, "
                    f"Uptime: {self.health.uptime_seconds:.1f}s"
                )
            
            except asyncio.CancelledError:
                break
            
            except Exception as e:
                logger.error(f"Health monitor error: {e}")
    
    async def _handle_reconnect(self) -> None:
        """Handle reconnection with exponential backoff."""
        self.reconnect_attempts += 1
        self.health.reconnects += 1
        self.health.state = ConnectionState.RECONNECTING
        
        if self.reconnect_attempts > self.config.max_reconnect_attempts:
            logger.error("Max reconnection attempts exceeded")
            self.health.state = ConnectionState.ERROR
            self.running = False
            if self.config.on_connection_lost:
                self.config.on_connection_lost()
            return
        
        # Exponential backoff
        delay = min(
            self.reconnect_delay,
            self.config.reconnect_max_delay,
        )
        
        logger.info(
            f"Reconnecting in {delay:.1f}s "
            f"(attempt {self.reconnect_attempts}/{self.config.max_reconnect_attempts})"
        )
        
        await asyncio.sleep(delay)
        self.reconnect_delay *= self.config.reconnect_backoff
    
    def get_health(self) -> ConnectionHealth:
        """Get connection health metrics."""
        return self.health
    
    def get_subscribed_symbols(self) -> Set[str]:
        """Get subscribed symbols."""
        return self.subscribed_symbols.copy()
    
    def get_buffer_stats(self) -> Dict[str, Any]:
        """Get buffer statistics."""
        return {
            "size": len(self.tick_buffer),
            "max_size": self.config.buffer_size,
            "utilization": len(self.tick_buffer) / self.config.buffer_size,
        }


# ============================================================================
# Fetcher Manager
# ============================================================================

class IDXFetcherManager:
    """Manages multiple data streams."""
    
    def __init__(self):
        """Initialize manager."""
        self.fetchers: Dict[str, IDXRealtimeFetcher] = {}
        self.api_clients: Dict[str, BEIWebSocketClient] = {}
        self.market_data_mgr: Optional[IDXMarketDataManager] = None
    
    def create_fetcher(
        self,
        name: str,
        username: str,
        password: str,
        config: Optional[StreamConfig] = None,
    ) -> IDXRealtimeFetcher:
        """Create and register a fetcher."""
        # Create API client
        api_client = BEIWebSocketClient(username, password)
        
        # Create market data manager if needed
        if self.market_data_mgr is None:
            self.market_data_mgr = IDXMarketDataManager()
        
        # Create fetcher
        fetcher = IDXRealtimeFetcher(
            api_client,
            self.market_data_mgr,
            config,
        )
        
        self.fetchers[name] = fetcher
        self.api_clients[name] = api_client
        
        return fetcher
    
    async def start_all(self) -> bool:
        """Start all fetchers."""
        results = []
        for fetcher in self.fetchers.values():
            result = await fetcher.start()
            results.append(result)
        
        return all(results) if results else False
    
    async def stop_all(self) -> bool:
        """Stop all fetchers."""
        results = []
        for fetcher in self.fetchers.values():
            result = await fetcher.stop()
            results.append(result)
        
        return all(results) if results else False
    
    def get_health_summary(self) -> Dict[str, Any]:
        """Get health summary for all fetchers."""
        summary = {
            "timestamp": get_jakarta_now().isoformat(),
            "fetchers": {},
        }
        
        for name, fetcher in self.fetchers.items():
            health = fetcher.get_health()
            summary["fetchers"][name] = {
                "state": health.state.value,
                "uptime": health.uptime_seconds,
                "ticks_received": health.ticks_received,
                "errors": health.errors,
                "reconnects": health.reconnects,
                "subscribed_symbols": list(fetcher.get_subscribed_symbols()),
            }
        
        return summary


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print("IDX Real-time Fetcher Module - Ready for import")
