"""
Tests for Chart Service and API
=================================

Comprehensive tests for TradingView chart integration.

Tests:
- Forex/Crypto symbol validation
- Chart metadata retrieval
- OHLCV data retrieval and aggregation
- TimeFrame support
- Jakarta timezone handling
- Market trading hours validation
- WebSocket connection simulation
- Cache functionality
- Error handling

Author: AutoSaham Team
"""

import pytest
import pandas as pd
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

from src.api.chart_service import (
    IDXSymbolValidator,
    MarketSymbolValidator,
    ChartMetadata,
    OHLCV,
    ChartDataCache,
    OHLCVAggregator,
    ChartService,
    TimeFrame,
    JAKARTA_TZ,
)


class TestMarketSymbolValidator:
    """Test Forex/Crypto symbol validation."""

    def test_valid_symbol_format(self):
        """Test valid Forex/Crypto symbol formats."""
        valid_symbols = ["EURUSD=X", "GBPUSD=X", "BTC-USD", "ETH-USD"]
        
        for symbol in valid_symbols:
            is_valid, error = MarketSymbolValidator.validate(symbol)
            assert is_valid, f"Symbol {symbol} should be valid: {error}"
            assert error is None

    def test_invalid_symbol_format(self):
        """Test invalid symbol formats."""
        invalid_symbols = [
            "BBCA.JK",  # Legacy IDX format should be rejected
            "INVALID",
            "123ABC",  # Invalid alpha pair
            "AAPL",  # Unsupported equity symbol
            "BTC--USD",
        ]
        
        for symbol in invalid_symbols:
            is_valid, error = MarketSymbolValidator.validate(symbol)
            assert not is_valid, f"Symbol {symbol} should be invalid"
            assert error is not None

    def test_symbol_metadata(self):
        """Test symbol metadata retrieval."""
        metadata = MarketSymbolValidator.get_metadata("EURUSD=X")
        
        assert metadata.symbol == "EURUSD=X"
        assert metadata.exchange == "FOREX"
        assert metadata.currency == "USD"
        assert metadata.min_lot_size == 0.01
        assert metadata.trading_start == "00:00"
        assert metadata.trading_end == "23:59"
        assert metadata.timezone == "Asia/Jakarta"

    def test_all_known_symbols(self):
        """Test all known market symbols."""
        for symbol in MarketSymbolValidator.SYMBOLS.keys():
            is_valid, error = MarketSymbolValidator.validate(symbol)
            assert is_valid, f"Symbol {symbol} should be valid: {error}"
            
            metadata = MarketSymbolValidator.get_metadata(symbol)
            assert metadata is not None

    def test_backward_compat_alias(self):
        """Ensure legacy IDXSymbolValidator import still works as alias."""
        is_valid, error = IDXSymbolValidator.validate("BTC-USD")
        assert is_valid
        assert error is None


class TestOHLCV:
    """Test OHLCV data structure."""

    def test_ohlcv_creation(self):
        """Test OHLCV object creation."""
        ohlcv = OHLCV(
            timestamp=1711933800,
            open=10250.00,
            high=10450.00,
            low=10200.00,
            close=10400.00,
            volume=25000000,
        )
        
        assert ohlcv.timestamp == 1711933800
        assert ohlcv.open == 10250.00
        assert ohlcv.close == 10400.00

    def test_ohlcv_to_dict(self):
        """Test OHLCV to dictionary conversion."""
        ohlcv = OHLCV(
            timestamp=1711933800,
            open=10250.00,
            high=10450.00,
            low=10200.00,
            close=10400.00,
            volume=25000000,
        )
        
        data = ohlcv.to_dict()
        assert data["timestamp"] == 1711933800
        assert data["close"] == 10400.00

    def test_ohlcv_lightweight_charts_format(self):
        """Test lightweight-charts JSON format."""
        ohlcv = OHLCV(
            timestamp=1711933800,
            open=10250.00,
            high=10450.00,
            low=10200.00,
            close=10400.00,
            volume=25000000,
        )
        
        chart_data = ohlcv.to_lightweight_charts_format()
        
        assert chart_data["time"] == 1711933800
        assert chart_data["open"] == 10250.0
        assert chart_data["high"] == 10450.0
        assert chart_data["low"] == 10200.0
        assert chart_data["close"] == 10400.0
        assert chart_data["volume"] == 25000000


class TestChartMetadata:
    """Test chart metadata."""

    def test_metadata_creation(self):
        """Test metadata creation."""
        metadata = ChartMetadata(
            symbol="BTC-USD",
            exchange="CRYPTO",
            currency="USD",
            timeframe=TimeFrame.D1,
            description="Bitcoin / US Dollar",
            decimal_places=2,
            min_lot_size=0.001,
            trading_start="00:00",
            trading_end="23:59",
            timezone="Asia/Jakarta",
        )
        
        assert metadata.symbol == "BTC-USD"
        assert metadata.exchange == "CRYPTO"

    def test_metadata_to_dict(self):
        """Test metadata to dictionary."""
        metadata = ChartMetadata(
            symbol="EURUSD=X",
            exchange="FOREX",
            currency="USD",
            timeframe=TimeFrame.D1,
            description="EUR/USD",
            decimal_places=5,
            min_lot_size=0.01,
            trading_start="00:00",
            trading_end="23:59",
            timezone="Asia/Jakarta",
        )
        
        data = metadata.to_dict()
        assert data["symbol"] == "EURUSD=X"
        assert data["exchange"] == "FOREX"
        assert data["currency"] == "USD"
        assert data["timeFrame"] == "1d"


class TestChartDataCache:
    """Test chart data cache."""

    def test_cache_set_and_get(self):
        """Test cache set and get operations."""
        cache = ChartDataCache(ttl_minutes=5)
        
        data = {"candles": []}
        cache.set("BTC-USD:1d:100", data)
        
        retrieved = cache.get("BTC-USD:1d:100")
        assert retrieved == data

    def test_cache_expiration(self):
        """Test cache expiration."""
        cache = ChartDataCache(ttl_minutes=0)  # Immediate expiration
        
        data = {"candles": []}
        cache.set("EURUSD=X:1d:100", data)
        
        # Wait a moment for time to pass
        import time
        time.sleep(0.1)
        
        retrieved = cache.get("EURUSD=X:1d:100")
        assert retrieved is None

    def test_cache_invalidate(self):
        """Test cache invalidation."""
        cache = ChartDataCache(ttl_minutes=5)
        
        cache.set("BTC-USD:1d:100", {})
        cache.set("EURUSD=X:1d:100", {})
        
        cache.invalidate("BTC-USD:1d:100")
        
        assert cache.get("BTC-USD:1d:100") is None
        assert cache.get("EURUSD=X:1d:100") is not None

    def test_cache_clear_all(self):
        """Test clearing entire cache."""
        cache = ChartDataCache(ttl_minutes=5)
        
        cache.set("BTC-USD:1d:100", {})
        cache.set("ETH-USD:1d:100", {})
        
        cache.invalidate()
        
        assert cache.get("BTC-USD:1d:100") is None
        assert cache.get("ETH-USD:1d:100") is None


class TestOHLCVAggregator:
    """Test OHLCV aggregation for different timeframes."""

    def test_resample_to_1h(self):
        """Test resampling to 1-hour timeframe."""
        # Create sample 5-minute data
        dates = pd.date_range(
            start="2024-04-01 09:30:00",
            periods=12,
            freq="5min",
            tz=JAKARTA_TZ,
        )
        
        df = pd.DataFrame({
            "open": [10250] * 12,
            "high": [10450] * 12,
            "low": [10200] * 12,
            "close": [10400] * 12,
            "volume": [1000000] * 12,
        }, index=dates)
        
        aggregator = OHLCVAggregator()
        candles = aggregator.resample_to_timeframe(df, TimeFrame.H1)
        
        assert len(candles) > 0
        assert candles[0].open == 10250.0
        assert candles[0].high == 10450.0

    def test_resample_to_daily(self):
        """Test resampling to daily timeframe."""
        dates = pd.date_range(
            start="2024-01-01",
            periods=30,
            freq="1h",
            tz=JAKARTA_TZ,
        )
        
        df = pd.DataFrame({
            "open": [10250] * 30,
            "high": [10450] * 30,
            "low": [10200] * 30,
            "close": [10400] * 30,
            "volume": [1000000] * 30,
        }, index=dates)
        
        aggregator = OHLCVAggregator()
        candles = aggregator.resample_to_timeframe(df, TimeFrame.D1)
        
        assert len(candles) > 0


class TestChartServiceTrading:
    """Test chart service trading hours functionality."""

    def test_is_trading_hours_weekday_open(self):
        """Test trading hours detection on weekday."""
        # Mock current time to Monday 10:00 WIB
        with patch('src.api.chart_service.datetime') as mock_datetime:
            mock_now = datetime(2024, 4, 1, 10, 0, 0, tzinfo=JAKARTA_TZ)  # Monday
            mock_datetime.now.return_value = mock_now
            mock_datetime.side_effect = lambda *args, **kw: datetime(*args, **kw)
            
            feature_store_mock = MagicMock()
            price_service_mock = MagicMock()
            
            service = ChartService(feature_store_mock, price_service_mock)
            
            # This test shows the concept; actual testing would need more setup

    def test_next_trading_time_after_hours(self):
        """Test next trading time calculation."""
        # Create service instance (with mocks)
        feature_store_mock = MagicMock()
        price_service_mock = MagicMock()
        
        service = ChartService(feature_store_mock, price_service_mock)
        next_open = service.get_next_trading_time()
        
        # Should return a datetime
        assert isinstance(next_open, datetime)
        # Should be in Jakarta timezone
        assert next_open.tzinfo is not None
        assert next_open.tzinfo.zone == "Asia/Jakarta"


class TestChartService:
    """Test main chart service."""

    @pytest.fixture
    def mock_service(self):
        """Create chart service with mocks."""
        feature_store = MagicMock()
        price_data_service = AsyncMock()
        
        service = ChartService(feature_store, price_data_service)
        return service, price_data_service

    @pytest.mark.asyncio
    async def test_get_chart_data_invalid_symbol(self, mock_service):
        """Test error handling for invalid symbol."""
        service, _ = mock_service
        
        from fastapi import HTTPException
        
        with pytest.raises(HTTPException) as exc_info:
            await service.get_chart_data("INVALID", "1d", 100)
        
        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_get_chart_data_success(self, mock_service):
        """Test successful chart data retrieval."""
        service, price_service = mock_service
        
        # Mock price data
        dates = pd.date_range(
            start="2024-01-01",
            periods=100,
            freq="1D",
            tz=JAKARTA_TZ,
        )
        df = pd.DataFrame({
            "open": [10250.0] * 100,
            "high": [10450.0] * 100,
            "low": [10200.0] * 100,
            "close": [10400.0] * 100,
            "volume": [25000000] * 100,
        }, index=dates)
        
        price_service.get_ohlcv.return_value = df
        
        data = await service.get_chart_data("BTC-USD", "1d", 100)
        
        assert "metadata" in data
        assert "candles" in data
        assert data["metadata"]["symbol"] == "BTC-USD"
        assert data["metadata"]["exchange"] == "CRYPTO"
        assert len(data["candles"]) > 0


# Integration tests
class TestChartIntegration:
    """Integration tests for chart service."""

    def test_symbol_validation_integration(self):
        """Test full symbol validation flow."""
        symbols_to_test = ["EURUSD=X", "BTC-USD", "ETH-USD"]
        
        for symbol in symbols_to_test:
            is_valid, error = MarketSymbolValidator.validate(symbol)
            assert is_valid
            
            metadata = MarketSymbolValidator.get_metadata(symbol)
            assert metadata.symbol == symbol
            assert metadata.exchange in {"FOREX", "CRYPTO"}
            assert metadata.currency in {"USD", "USDT", "USDC", "JPY"}

    def test_cache_integration(self):
        """Test cache integration with chart data."""
        cache = ChartDataCache(ttl_minutes=5)
        
        # Simulate multiple requests for same data
        key = "BTC-USD:1d:100"
        data = {"candles": []}
        
        cache.set(key, data)
        retrieved1 = cache.get(key)
        retrieved2 = cache.get(key)
        
        assert retrieved1 == data
        assert retrieved2 == data


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
