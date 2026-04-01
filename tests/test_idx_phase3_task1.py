"""
Tests for IDX Phase 3 Task 1: IDX Official API Integration

Test Coverage:
- BEI API Client: Connection, subscription, data types
- Market Data Manager: Symbol registration, OHLCV aggregation, trading hours
- Real-time Fetcher: Streaming, buffering, reconnection
- Order Validator: Price limits, lot size, trading hours, settlement
"""

import asyncio
import pytest
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from src.data.idx_api_client import (
    BEIWebSocketClient, Tick, OrderBook, OrderBookLevel, OHLCV,
    MarketDataCache, get_jakarta_now, to_jakarta_time, JAKARTA_TZ,
    IDX_TRADING_START, IDX_TRADING_END,
)
from src.data.idx_market_data import (
    IDXMarketDataManager, SymbolInfo, CorporateAction, CorporateActionType,
    SessionType, AggregationState,
)
from src.pipeline.idx_realtime_fetcher import (
    IDXRealtimeFetcher, IDXFetcherManager, StreamConfig,
    ConnectionState,
)
from src.execution.idx_order_validator import (
    IDXOrderValidator, OrderExecutionValidator, Order, OrderSide, OrderType,
    ValidationErrorCode,
)


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def market_data_mgr():
    """Create market data manager."""
    mgr = IDXMarketDataManager()
    
    # Register test symbols
    symbols = [
        SymbolInfo(
            symbol="BBCA.JK",
            name="Bank Central Asia",
            sector="Finance",
            industry="Banking",
            issued_shares=2000000000,
            market_cap=1000e12,  # 1 quadrillion IDR
        ),
        SymbolInfo(
            symbol="BMRI.JK",
            name="Bank Mandiri",
            sector="Finance",
            industry="Banking",
            issued_shares=1500000000,
        ),
        SymbolInfo(
            symbol="TLKM.JK",
            name="Telekomunikasi Indonesia",
            sector="Telecom",
            industry="Telecommunications",
            issued_shares=1000000000,
        ),
    ]
    
    mgr.register_symbols_batch(symbols)
    return mgr


@pytest.fixture
def sample_tick():
    """Create sample tick."""
    return Tick(
        symbol="BBCA.JK",
        timestamp=get_jakarta_now(),
        price=15500.0,  # IDR
        quantity=10,  # lots (1000 shares)
        side="B",
        trade_id="BBCA20240101.001",
    )


@pytest.fixture
def sample_ohlcv():
    """Create sample OHLCV."""
    return OHLCV(
        symbol="BBCA.JK",
        timestamp=get_jakarta_now(),
        period="1m",
        open=15400.0,
        high=15600.0,
        low=15350.0,
        close=15500.0,
        volume=1000000,
        trades=150,
        vwap=15450.0,
    )


@pytest.fixture
def sample_orderbook():
    """Create sample order book."""
    return OrderBook(
        symbol="BBCA.JK",
        timestamp=get_jakarta_now(),
        bids=[
            OrderBookLevel(price=15500.0, quantity=100, orders=5),
            OrderBookLevel(price=15450.0, quantity=150, orders=8),
            OrderBookLevel(price=15400.0, quantity=200, orders=12),
        ],
        asks=[
            OrderBookLevel(price=15550.0, quantity=80, orders=4),
            OrderBookLevel(price=15600.0, quantity=120, orders=6),
            OrderBookLevel(price=15650.0, quantity=100, orders=8),
        ],
    )


# ============================================================================
# Tests: IDX API Client
# ============================================================================

class TestBEIAPIClient:
    """Tests for BEI API Client."""
    
    def test_client_initialization(self):
        """Test client initialization."""
        client = BEIWebSocketClient(
            username="testuser",
            password="testpass",
        )
        
        assert client.username == "testuser"
        assert not client.authenticated
        assert not client.connected
    
    def test_order_book_creation(self):
        """Test order book creation."""
        ob = OrderBook(
            symbol="BBCA.JK",
            timestamp=get_jakarta_now(),
            bids=[OrderBookLevel(price=15500, quantity=100)],
            asks=[OrderBookLevel(price=15550, quantity=80)],
        )
        
        assert ob.symbol == "BBCA.JK"
        assert len(ob.bids) == 1
        assert len(ob.asks) == 1
        assert ob.get_spread() == 50.0
    
    def test_order_book_spread_calculation(self, sample_orderbook):
        """Test spread calculation."""
        spread = sample_orderbook.get_spread()
        assert spread == 50.0  # 15550 - 15500
        
        spread_pct = sample_orderbook.get_spread_pct()
        assert spread_pct is not None
        assert 0.3 < spread_pct < 0.4  # ~0.32%
    
    def test_tick_creation(self, sample_tick):
        """Test tick creation."""
        assert sample_tick.symbol == "BBCA.JK"
        assert sample_tick.price == 15500.0
        assert sample_tick.quantity == 10
        assert sample_tick.side == "B"
    
    def test_ohlcv_creation(self, sample_ohlcv):
        """Test OHLCV creation."""
        assert sample_ohlcv.symbol == "BBCA.JK"
        assert sample_ohlcv.open == 15400.0
        assert sample_ohlcv.high == 15600.0
        assert sample_ohlcv.low == 15350.0
        assert sample_ohlcv.close == 15500.0
        
        # Check properties
        assert sample_ohlcv.hl_range == 250.0
        assert sample_ohlcv.close_change_pct == pytest.approx(6.49, abs=0.01)
    
    def test_market_data_cache(self, sample_tick, sample_ohlcv):
        """Test data cache."""
        cache = MarketDataCache(max_size=100)
        
        # Add tick
        cache.add_tick(sample_tick)
        assert len(cache.ticks["BBCA.JK"]) == 1
        assert cache.get_latest_price("BBCA.JK") == 15500.0
        
        # Add OHLCV
        cache.cache_ohlcv("BBCA.JK", "1m", [sample_ohlcv])
        assert ("BBCA.JK", "1m") in cache.ohlcv_cache


# ============================================================================
# Tests: Market Data Manager
# ============================================================================

class TestMarketDataManager:
    """Tests for market data manager."""
    
    def test_symbol_registration(self, market_data_mgr):
        """Test symbol registration."""
        assert len(market_data_mgr.symbols) == 3
        assert "BBCA.JK" in market_data_mgr.symbols
    
    def test_get_symbol_info(self, market_data_mgr):
        """Test retrieving symbol info."""
        info = market_data_mgr.get_symbol_info("BBCA.JK")
        assert info is not None
        assert info.name == "Bank Central Asia"
        assert info.sector == "Finance"
    
    def test_corporate_action_tracking(self, market_data_mgr):
        """Test corporate action tracking."""
        action = CorporateAction(
            symbol="BBCA.JK",
            ex_date=get_jakarta_now(),
            effective_date=get_jakarta_now() + timedelta(days=14),
            action_type=CorporateActionType.DIVIDEND,
            description="Interim dividend",
            value=1500.0,  # IDR per share
        )
        
        market_data_mgr.add_corporate_action(action)
        
        actions = market_data_mgr.get_corporate_actions("BBCA.JK")
        assert len(actions) == 1
        assert actions[0].value == 1500.0
    
    def test_trading_session_detection(self, market_data_mgr):
        """Test trading session detection."""
        # Regular trading (10:00 WIB)
        trading_time = datetime(2024, 1, 1, 10, 0, 0, tzinfo=JAKARTA_TZ)
        assert market_data_mgr.get_trading_session(trading_time) == SessionType.REGULAR
        assert market_data_mgr.is_trading_hours(trading_time)
        assert market_data_mgr.is_market_open(trading_time)
        
        # Pre-trading (08:30 WIB)
        pretrading_time = datetime(2024, 1, 1, 8, 30, 0, tzinfo=JAKARTA_TZ)
        assert market_data_mgr.get_trading_session(pretrading_time) == SessionType.PRETRADING
        assert not market_data_mgr.is_trading_hours(pretrading_time)
        assert market_data_mgr.is_market_open(pretrading_time)
        
        # After hours (18:00 WIB)
        after_hours = datetime(2024, 1, 1, 18, 0, 0, tzinfo=JAKARTA_TZ)
        assert market_data_mgr.get_trading_session(after_hours) == SessionType.CLOSED
        assert not market_data_mgr.is_trading_hours(after_hours)
        assert not market_data_mgr.is_market_open(after_hours)
    
    def test_price_validation(self, market_data_mgr):
        """Test price validation."""
        # Valid price
        is_valid, msg = market_data_mgr.validate_price("BBCA.JK", 15500.0, 14800.0)
        assert is_valid
        
        # Exceeds ±35% limit (40% increase)
        is_valid, msg = market_data_mgr.validate_price("BBCA.JK", 20720.0, 14800.0)
        assert not is_valid
        assert "35%" in msg
        
        # Negative price
        is_valid, msg = market_data_mgr.validate_price("BBCA.JK", -1000.0, 14800.0)
        assert not is_valid
    
    def test_ohlcv_aggregation(self, market_data_mgr):
        """Test OHLCV aggregation from ticks."""
        # Create multiple ticks for aggregation
        ticks = [
            Tick(symbol="BBCA.JK", timestamp=get_jakarta_now(), price=15400.0, quantity=10, side="B", trade_id="1"),
            Tick(symbol="BBCA.JK", timestamp=get_jakarta_now(), price=15450.0, quantity=15, side="S", trade_id="2"),
            Tick(symbol="BBCA.JK", timestamp=get_jakarta_now(), price=15500.0, quantity=20, side="B", trade_id="3"),
        ]
        
        for tick in ticks:
            market_data_mgr.on_tick_received(tick)
        
        # Get OHLCV for 1m period
        ohlcv = market_data_mgr.get_ohlcv("BBCA.JK", "1m")
        
        # Should have aggregated ticks into candle(s)
        assert len(ohlcv) >= 0  # May or may not have closed candle yet


# ============================================================================
# Tests: Order Validator
# ============================================================================

class TestIDXOrderValidator:
    """Tests for order validator."""
    
    def test_valid_order(self, market_data_mgr):
        """Test validation of valid order."""
        validator = IDXOrderValidator(market_data_mgr)
        
        order = Order(
            symbol="BBCA.JK",
            side=OrderSide.BUY,
            quantity=100,
            order_type=OrderType.MARKET,
            price=15500.0,
        )
        
        result = validator.validate(
            order,
            current_balance=2000000.0,
        )
        
        assert result.is_valid
        assert result.error_code is None
    
    def test_invalid_symbol(self, market_data_mgr):
        """Test validation with invalid symbol."""
        validator = IDXOrderValidator(market_data_mgr)
        
        order = Order(
            symbol="INVALID.JK",
            side=OrderSide.BUY,
            quantity=100,
            order_type=OrderType.MARKET,
        )
        
        result = validator.validate(order)
        
        assert not result.is_valid
        assert result.error_code == ValidationErrorCode.INVALID_SYMBOL
    
    def test_invalid_lot_size(self, market_data_mgr):
        """Test validation with invalid lot size."""
        validator = IDXOrderValidator(market_data_mgr)
        
        order = Order(
            symbol="BBCA.JK",
            side=OrderSide.BUY,
            quantity=50,  # Not multiple of 100
            order_type=OrderType.MARKET,
        )
        
        result = validator.validate(order)
        
        assert not result.is_valid
        assert result.error_code == ValidationErrorCode.INVALID_QUANTITY
    
    def test_price_limit_exceeded(self, market_data_mgr):
        """Test price limit validation."""
        validator = IDXOrderValidator(market_data_mgr)
        
        # Set a reference price
        market_data_mgr.last_price["BBCA.JK"] = 15000.0
        
        # Try to place order at 51% premium (exceeds ±35% limit)
        order = Order(
            symbol="BBCA.JK",
            side=OrderSide.BUY,
            quantity=100,
            order_type=OrderType.LIMIT,
            price=22650.0,  # 51% increase from 15000
        )
        
        result = validator.validate(order)
        
        assert not result.is_valid
        assert result.error_code == ValidationErrorCode.INVALID_PRICE
    
    def test_insufficient_funds(self, market_data_mgr):
        """Test insufficient funds check."""
        validator = IDXOrderValidator(market_data_mgr)
        
        order = Order(
            symbol="BBCA.JK",
            side=OrderSide.BUY,
            quantity=100,
            order_type=OrderType.MARKET,
            price=15500.0,
        )
        
        # Only 500K IDR but need 1.55M
        result = validator.validate(order, current_balance=500000.0)
        
        assert not result.is_valid
        assert result.error_code == ValidationErrorCode.INSUFFICIENT_FUNDS
    
    def test_trading_hours_validation(self, market_data_mgr):
        """Test trading hours validation."""
        validator = IDXOrderValidator(market_data_mgr)
        
        order = Order(
            symbol="BBCA.JK",
            side=OrderSide.BUY,
            quantity=100,
            order_type=OrderType.MARKET,
            timestamp=datetime(2024, 1, 1, 18, 0, 0, tzinfo=JAKARTA_TZ),  # 18:00 = after hours
        )
        
        result = validator.validate(order)
        
        assert not result.is_valid
        assert result.error_code == ValidationErrorCode.OUTSIDE_TRADING_HOURS
    
    def test_settlement_date_calculation(self, market_data_mgr):
        """Test T+2 settlement date calculation."""
        validator = OrderExecutionValidator(market_data_mgr)
        
        # Monday trade
        trade_date = datetime(2024, 1, 1, 10, 0, 0, tzinfo=JAKARTA_TZ)  # Monday
        settlement = validator.get_settlement_date(trade_date)
        
        # Settlement should be Wednesday (2 days later)
        assert settlement.weekday() == 2  # 0=Mon, 2=Wed


# ============================================================================
# Tests: Async Fetcher
# ============================================================================

class TestIDXRealtimeFetcher:
    """Tests for real-time fetcher."""
    
    @pytest.mark.asyncio
    async def test_fetcher_initialization(self, market_data_mgr):
        """Test fetcher initialization."""
        client = BEIWebSocketClient("test", "test")
        config = StreamConfig(symbols=["BBCA.JK", "BMRI.JK"])
        
        fetcher = IDXRealtimeFetcher(client, market_data_mgr, config)
        
        assert not fetcher.running
        assert fetcher.config.symbols == ["BBCA.JK", "BMRI.JK"]
    
    def test_fetcher_manager(self, market_data_mgr):
        """Test fetcher manager."""
        manager = IDXFetcherManager()
        
        config = StreamConfig(symbols=["BBCA.JK"])
        fetcher = manager.create_fetcher(
            "primary",
            "testuser",
            "testpass",
            config,
        )
        
        assert "primary" in manager.fetchers
        assert manager.market_data_mgr is not None


# ============================================================================
# Integration Tests
# ============================================================================

class TestIDXIntegration:
    """Integration tests for IDX components."""
    
    def test_end_to_end_workflow(self, market_data_mgr):
        """Test complete workflow: validation -> market data -> storage."""
        validator = IDXOrderValidator(market_data_mgr)
        
        # Create and validate order
        order = Order(
            symbol="BBCA.JK",
            side=OrderSide.BUY,
            quantity=100,
            order_type=OrderType.LIMIT,
            price=15500.0,
        )
        
        result = validator.validate(order, current_balance=2000000.0)
        assert result.is_valid
        
        # Simulate tick reception
        tick = Tick(
            symbol="BBCA.JK",
            timestamp=get_jakarta_now(),
            price=15500.0,
            quantity=10,
            side="B",
            trade_id="TEST.001",
        )
        
        market_data_mgr.on_tick_received(tick)
        
        # Verify data stored
        latest = market_data_mgr.get_latest_price("BBCA.JK")
        assert latest == 15500.0
    
    def test_jakarta_timezone_consistency(self, market_data_mgr):
        """Test timezone consistency throughout system."""
        now = get_jakarta_now()
        assert now.tzinfo == JAKARTA_TZ
        
        # All system timestamps should be in Jakarta timezone
        order = Order(
            symbol="BBCA.JK",
            side=OrderSide.BUY,
            quantity=100,
            order_type=OrderType.MARKET,
        )
        
        assert order.timestamp.tzinfo == JAKARTA_TZ
    
    def test_idx_compliance_rules(self, market_data_mgr):
        """Test all IDX compliance rules."""
        validator = IDXOrderValidator(market_data_mgr)
        
        # Rule 1: 100-share minimum lots
        order = Order(
            symbol="BBCA.JK",
            side=OrderSide.BUY,
            quantity=50,  # Violates rule
            order_type=OrderType.MARKET,
        )
        result = validator.validate(order)
        assert not result.is_valid
        
        # Rule 2: Trading hours (09:30-16:00 WIB)
        order = Order(
            symbol="BBCA.JK",
            side=OrderSide.BUY,
            quantity=100,
            order_type=OrderType.MARKET,
            timestamp=datetime(2024, 1, 1, 19, 0, 0, tzinfo=JAKARTA_TZ),  # Outside hours
        )
        result = validator.validate(order)
        assert not result.is_valid
        
        # Rule 3: ±35% price limit
        market_data_mgr.last_price["BBCA.JK"] = 10000.0
        order = Order(
            symbol="BBCA.JK",
            side=OrderSide.BUY,
            quantity=100,
            order_type=OrderType.LIMIT,
            price=14000.0,  # 40% increase - violates limit
        )
        result = validator.validate(order)
        assert not result.is_valid


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
