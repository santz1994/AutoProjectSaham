"""
IDX Market Data Integration Layer
==================================

Task 1 (Phase 3): Market data aggregation and validation

Features:
- Real-time OHLCV aggregation from BEI API
- Corporate actions handling (dividends, splits)
- Data quality checks
- IDX trading hours enforcement
- Jakarta timezone management
"""

import asyncio
import logging
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Dict, List, Optional, Set, Tuple, Any, Callable
from collections import deque

try:
    import pandas as pd
    PANDAS_AVAILABLE = True
except ImportError:
    PANDAS_AVAILABLE = False

from .idx_api_client import (
    OHLCV, Tick, OrderBook, MarketDataCache,
    JAKARTA_TZ, get_jakarta_now, to_jakarta_time,
    IDX_TRADING_START, IDX_TRADING_END,
    IDX_PRETRADING_START, IDX_PRETRADING_END,
)


logger = logging.getLogger(__name__)


# ============================================================================
# Enums
# ============================================================================

class CorporateActionType(Enum):
    """Type of corporate action."""
    DIVIDEND = "dividend"
    BONUS = "bonus"
    SPLIT = "split"
    REVERSE_SPLIT = "reverse_split"
    IPO = "ipo"
    DELISTING = "delisting"
    NAME_CHANGE = "name_change"


class SessionType(Enum):
    """IDX trading session type."""
    PRETRADING = "pretrading"  # 08:00 - 09:29
    REGULAR = "regular"  # 09:30 - 16:00
    CLOSED = "closed"


# ============================================================================
# Data Classes
# ============================================================================

@dataclass
class CorporateAction:
    """Corporate action event."""
    symbol: str
    ex_date: datetime  # Ex-date (When action takes effect)
    effective_date: datetime  # When dividend/payment is made
    action_type: CorporateActionType
    description: str
    value: Optional[float] = None  # Dividend amount in IDR per share, or split ratio
    ratio: Optional[float] = None  # For splits/bonus (new : old)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbol": self.symbol,
            "ex_date": self.ex_date.isoformat(),
            "effective_date": self.effective_date.isoformat(),
            "action_type": self.action_type.value,
            "description": self.description,
            "value": self.value,
            "ratio": self.ratio,
        }


@dataclass
class SymbolInfo:
    """Information about a stock symbol."""
    symbol: str
    name: str
    sector: str
    industry: str
    issued_shares: int
    market_cap: Optional[float] = None  # IDR
    lot_size: int = 100
    price_min: float = 50  # Minimum price
    price_max: float = 500000  # Maximum price
    price_decimals: int = 2
    active: bool = True
    last_updated: datetime = field(default_factory=get_jakarta_now)
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class AggregationState:
    """State for OHLCV aggregation."""
    symbol: str
    period_start: datetime
    period: str  # "1m", "5m", "1h", "1d"
    
    open: Optional[float] = None
    high: float = 0.0
    low: float = float('inf')
    close: Optional[float] = None
    volume: int = 0
    trades: int = 0
    tick_count: int = 0
    tick_prices: List[float] = field(default_factory=list)
    vwap_sum: float = 0.0
    vwap_vol: int = 0


# ============================================================================
# IDX Market Data Manager
# ============================================================================

class IDXMarketDataManager:
    """
    Manages market data for IDX stocks.
    
    Responsibilities:
    - Real-time OHLCV aggregation
    - Corporate action tracking
    - Data quality validation
    - Trading hours management
    - Symbol information
    """
    
    def __init__(self, cache_size: int = 10000):
        """
        Initialize manager.
        
        Args:
            cache_size: Market data cache size
        """
        self.cache = MarketDataCache(cache_size)
        self.symbols: Dict[str, SymbolInfo] = {}
        self.corporate_actions: Dict[str, List[CorporateAction]] = {}
        
        # OHLCV aggregation state
        self.agg_state: Dict[Tuple[str, str], AggregationState] = {}
        
        # Quality metrics
        self.data_quality: Dict[str, float] = {}  # symbol -> quality score (0-1)
        self.last_price: Dict[str, float] = {}
        self.last_update: Dict[str, datetime] = {}
        
        # Callbacks
        self.on_tick: List[Callable[[Tick], None]] = []
        self.on_ohlcv: List[Callable[[OHLCV], None]] = []
        self.on_orderbook: List[Callable[[OrderBook], None]] = []
    
    def register_symbol(self, symbol_info: SymbolInfo) -> None:
        """Register a stock symbol."""
        self.symbols[symbol_info.symbol] = symbol_info
        self.corporate_actions[symbol_info.symbol] = []
        logger.info(f"Registered symbol: {symbol_info.symbol}")
    
    def register_symbols_batch(self, symbols: List[SymbolInfo]) -> None:
        """Register multiple symbols."""
        for symbol in symbols:
            self.register_symbol(symbol)
    
    def add_corporate_action(self, action: CorporateAction) -> None:
        """Add corporate action."""
        if action.symbol not in self.corporate_actions:
            self.corporate_actions[action.symbol] = []
        
        self.corporate_actions[action.symbol].append(action)
        logger.info(
            f"Added corporate action: {action.symbol} "
            f"{action.action_type.value} on {action.ex_date}"
        )
    
    def get_corporate_actions(
        self,
        symbol: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> List[CorporateAction]:
        """Get corporate actions for a symbol."""
        if symbol not in self.corporate_actions:
            return []
        
        actions = self.corporate_actions[symbol]
        
        if start_date:
            actions = [a for a in actions if a.ex_date >= start_date]
        if end_date:
            actions = [a for a in actions if a.ex_date <= end_date]
        
        return sorted(actions, key=lambda a: a.ex_date)
    
    def on_tick_received(self, tick: Tick) -> None:
        """Handle incoming tick data."""
        # Add to cache
        self.cache.add_tick(tick)
        
        # Update latest price
        self.last_price[tick.symbol] = tick.price
        self.last_update[tick.symbol] = tick.timestamp
        
        # Update aggregation states
        self._update_aggregations(tick)
        
        # Call callbacks
        for callback in self.on_tick:
            try:
                callback(tick)
            except Exception as e:
                logger.error(f"Tick callback error: {e}")
    
    def on_orderbook_received(self, orderbook: OrderBook) -> None:
        """Handle order book updates."""
        self.cache.add_order_book(orderbook)
        
        for callback in self.on_orderbook:
            try:
                callback(orderbook)
            except Exception as e:
                logger.error(f"OrderBook callback error: {e}")
    
    def _update_aggregations(self, tick: Tick) -> None:
        """Update OHLCV aggregation states."""
        # Update all active aggregation periods
        for period in ["1m", "5m", "1h", "1d"]:
            key = (tick.symbol, period)
            
            # Get or create aggregation state
            if key not in self.agg_state:
                self._init_aggregation(tick, period)
            
            state = self.agg_state[key]
            
            # Check if period elapsed
            elapsed = (tick.timestamp - state.period_start).total_seconds()
            period_seconds = self._get_period_seconds(period)
            
            if elapsed >= period_seconds:
                # Period complete - emit OHLCV
                self._emit_ohlcv(state)
                
                # Start new period
                self._init_aggregation(tick, period)
                state = self.agg_state[key]
            
            # Update state with tick
            self._aggregate_tick(state, tick)
    
    def _init_aggregation(self, tick: Tick, period: str) -> None:
        """Initialize aggregation state."""
        key = (tick.symbol, period)
        period_seconds = self._get_period_seconds(period)
        
        # Round timestamp to period boundary
        ts = tick.timestamp
        ts_seconds = ts.timestamp()
        period_start = ts_seconds - (ts_seconds % period_seconds)
        period_start_dt = datetime.fromtimestamp(period_start, tz=JAKARTA_TZ)
        
        self.agg_state[key] = AggregationState(
            symbol=tick.symbol,
            period_start=period_start_dt,
            period=period,
        )
    
    def _aggregate_tick(self, state: AggregationState, tick: Tick) -> None:
        """Add tick to aggregation state."""
        # Open (first tick)
        if state.open is None:
            state.open = tick.price
        
        # High/Low
        state.high = max(state.high, tick.price)
        state.low = min(state.low, tick.price)
        
        # Close (latest)
        state.close = tick.price
        
        # Volume
        state.volume += tick.quantity * state.lot_size  # Convert lots to shares
        
        # Trades
        state.trades += 1
        state.tick_count += 1
        
        # VWAP calculation
        state.tick_prices.append(tick.price)
        state.vwap_sum += tick.price * (tick.quantity * state.lot_size)
        state.vwap_vol += tick.quantity * state.lot_size
    
    def _emit_ohlcv(self, state: AggregationState) -> None:
        """Emit completed OHLCV candle."""
        if state.open is None:
            return  # No data for this period
        
        vwap = (
            state.vwap_sum / state.vwap_vol
            if state.vwap_vol > 0 else None
        )
        
        ohlcv = OHLCV(
            symbol=state.symbol,
            timestamp=state.period_start,
            period=state.period,
            open=state.open,
            high=state.high,
            low=state.low,
            close=state.close,
            volume=state.volume,
            trades=state.trades,
            vwap=vwap,
        )
        
        # Cache OHLCV
        key = (state.symbol, state.period)
        if key not in self.cache.ohlcv_cache:
            self.cache.ohlcv_cache[key] = []
        self.cache.ohlcv_cache[key].append(ohlcv)
        
        # Call callbacks
        for callback in self.on_ohlcv:
            try:
                callback(ohlcv)
            except Exception as e:
                logger.error(f"OHLCV callback error: {e}")
    
    def _get_period_seconds(self, period: str) -> int:
        """Get period duration in seconds."""
        periods = {
            "1m": 60,
            "5m": 300,
            "15m": 900,
            "1h": 3600,
            "4h": 14400,
            "1d": 86400,
        }
        return periods.get(period, 60)
    
    def validate_price(
        self,
        symbol: str,
        price: float,
        previous_close: float,
    ) -> Tuple[bool, Optional[str]]:
        """
        Validate price for IDX trading rules.
        
        Rules:
        - Price cannot change more than ±35% from previous close
        - Price must be positive
        - Price must be in valid range for symbol
        
        Returns:
            (is_valid, error_message)
        """
        # Check positive
        if price <= 0:
            return False, f"Price must be positive: {price}"
        
        # Check symbol info
        if symbol in self.symbols:
            info = self.symbols[symbol]
            if price < info.price_min or price > info.price_max:
                return False, f"Price {price} outside range [{info.price_min}, {info.price_max}]"
        
        # Check ±35% limit
        if previous_close > 0:
            change_pct = abs((price - previous_close) / previous_close) * 100
            if change_pct > 35:
                return False, f"Price change {change_pct:.2f}% exceeds ±35% limit"
        
        return True, None
    
    def get_trading_session(self, timestamp: Optional[datetime] = None) -> SessionType:
        """Get current or given time's trading session."""
        if timestamp is None:
            timestamp = get_jakarta_now()
        
        timestamp = to_jakarta_time(timestamp)
        time_str = timestamp.strftime("%H:%M")
        
        if IDX_PRETRADING_START <= time_str < IDX_PRETRADING_END:
            return SessionType.PRETRADING
        elif IDX_TRADING_START <= time_str < IDX_TRADING_END:
            return SessionType.REGULAR
        else:
            return SessionType.CLOSED
    
    def is_trading_hours(self, timestamp: Optional[datetime] = None) -> bool:
        """Check if within trading hours (not including pre-trading)."""
        session = self.get_trading_session(timestamp)
        return session == SessionType.REGULAR
    
    def is_market_open(self, timestamp: Optional[datetime] = None) -> bool:
        """Check if market is open (including pre-trading)."""
        session = self.get_trading_session(timestamp)
        return session in [SessionType.PRETRADING, SessionType.REGULAR]
    
    def get_symbol_info(self, symbol: str) -> Optional[SymbolInfo]:
        """Get symbol information."""
        return self.symbols.get(symbol)
    
    def get_latest_price(self, symbol: str) -> Optional[float]:
        """Get latest known price."""
        return self.last_price.get(symbol)
    
    def get_ohlcv(
        self,
        symbol: str,
        period: str = "1m",
        limit: int = 100,
    ) -> List[OHLCV]:
        """Get OHLCV data."""
        key = (symbol, period)
        if key in self.cache.ohlcv_cache:
            return self.cache.ohlcv_cache[key][-limit:]
        return []
    
    def get_dataframe(
        self,
        symbol: str,
        period: str = "1m",
    ) -> Optional[pd.DataFrame]:
        """Get OHLCV as pandas DataFrame."""
        if not PANDAS_AVAILABLE:
            logger.warning("pandas not available")
            return None
        
        ohlcv_list = self.get_ohlcv(symbol, period)
        if not ohlcv_list:
            return None
        
        data = [o.to_dict() for o in ohlcv_list]
        df = pd.DataFrame(data)
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        df.set_index("timestamp", inplace=True)
        
        return df
    
    def clear_cache(self) -> None:
        """Clear all caches."""
        self.cache.clear()
        self.agg_state.clear()
        self.data_quality.clear()
        logger.info("Market data cache cleared")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print("IDX Market Data Integration Module - Ready for import")
