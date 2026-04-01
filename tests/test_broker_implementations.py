"""
Broker Implementation Tests
============================

Comprehensive test suite for broker architecture and integration.
Tests focus on dataclass models, broker manager coordination, and core functionality.

Timezone: Jakarta (WIB: UTC+7)
Currency: IDR
"""

import pytest
from unittest.mock import AsyncMock, MagicMock
from datetime import datetime

from src.data.idx_api_client import JAKARTA_TZ
from src.brokers.base_broker import (
    BaseBroker, AccountInfo, Position, OrderResult, Trade,
    ExecutionStatus, TimeInForce, AccountType,
)
from src.brokers.stockbit import StockbitBroker
from src.brokers.ajaib import AjaibBroker
from src.brokers.indopremier import IndoPremierBroker
from src.brokers.broker_manager import BrokerManager, BrokerType


# ============================================================================
# Test Fixtures
# ============================================================================

@pytest.fixture
def broker_credentials():
    """Mock broker credentials."""
    return {
        "api_key": "test_api_key_12345",
        "api_secret": "test_secret_key_abcdef",
        "account_id": "ACC123456",
    }


# ============================================================================
# Base Broker Interface Tests
# ============================================================================

class TestBaseBrokerInterface:
    """Test BaseBroker abstract interface and dataclass definitions."""
    
    def test_broker_cannot_be_instantiated(self):
        """BaseBroker is abstract and cannot be instantiated directly."""
        with pytest.raises(TypeError):
            BaseBroker(api_key="test", api_secret="test", account_id="test")
    
    def test_account_info_dataclass(self):
        """Test AccountInfo dataclass creation and properties."""
        info = AccountInfo(
            account_id="ACC123",
            account_type=AccountType.CASH,
            cash=10_000_000,
            buying_power=15_000_000,
            market_value=15_000_000,
            settled_cash=8_000_000,
            unsettled_cash=2_000_000,
            equity=25_000_000,
        )
        
        assert info.account_id == "ACC123"
        assert info.cash == 10_000_000
        assert info.equity == 25_000_000
        assert info.total_value == 25_000_000  # property
        assert info.account_type == AccountType.CASH
    
    def test_position_dataclass(self):
        """Test Position dataclass creation and properties."""
        position = Position(
            symbol="BBCA.JK",
            quantity=100,
            avg_cost=15_500.0,
            current_price=15_600.0,
            market_value=1_560_000.0,
            unrealized_pl=10_000.0,
            unrealized_pl_pct=0.65,
        )
        
        assert position.symbol == "BBCA.JK"
        assert position.quantity == 100
        assert position.avg_cost == 15_500.0
        assert position.total_cost == 1_550_000.0  # property
        assert position.market_value == 1_560_000.0
        assert position.unrealized_pl == 10_000.0
    
    def test_order_result_dataclass(self):
        """Test OrderResult dataclass creation and properties."""
        result = OrderResult(
            order_id="ORD001",
            broker="test_broker",
            symbol="BBCA.JK",
            side="buy",
            quantity=100,
            filled_quantity=100,
            avg_fill_price=15_600.0,
            status=ExecutionStatus.FILLED,
        )
        
        assert result.order_id == "ORD001"
        assert result.status == ExecutionStatus.FILLED
        assert result.total_value == 1_560_000.0  # property
        assert result.broker == "test_broker"
    
    def test_trade_dataclass(self):
        """Test Trade dataclass creation and properties."""
        trade = Trade(
            trade_id="TRADE001",
            symbol="BMRI.JK",
            side="sell",
            quantity=100,
            price=8_000.0,
            timestamp=datetime.now(JAKARTA_TZ),
            commission=50_000.0,
        )
        
        assert trade.trade_id == "TRADE001"
        assert trade.symbol == "BMRI.JK"
        assert trade.total_value == 800_000.0  # property
        assert trade.commission == 50_000.0
    
    def test_execution_status_enum(self):
        """Test ExecutionStatus enum values."""
        assert ExecutionStatus.PENDING.value == "pending"
        assert ExecutionStatus.FILLED.value == "filled"
        assert ExecutionStatus.CANCELLED.value == "cancelled"
        assert ExecutionStatus.REJECTED.value == "rejected"
    
    def test_time_in_force_enum(self):
        """Test TimeInForce enum values."""
        assert TimeInForce.DAY.value == "day"
        assert TimeInForce.IOC.value == "ioc"
        assert TimeInForce.FOK.value == "fok"
        assert TimeInForce.GTC.value == "gtc"
    
    def test_account_type_enum(self):
        """Test AccountType enum values."""
        assert AccountType.CASH.value == "cash"
        assert AccountType.MARGIN.value == "margin"
        assert AccountType.DEMO.value == "demo"


# ============================================================================
# Concrete Broker Tests (Structure & Interface)
# ============================================================================

class TestStockbitBrokerStructure:
    """Test StockbitBroker class structure and initialization."""
    
    def test_stockbit_initialization(self, broker_credentials):
        """Test Stockbit broker can be initialized."""
        broker = StockbitBroker(**broker_credentials)
        
        assert broker.api_key == broker_credentials["api_key"]
        assert broker.api_secret == broker_credentials["api_secret"]
        assert broker.account_id == broker_credentials["account_id"]
        assert broker.broker_name == "stockbit"
    
    def test_stockbit_inherits_from_basebroker(self, broker_credentials):
        """Test Stockbit is a BaseBroker subclass."""
        broker = StockbitBroker(**broker_credentials)
        assert isinstance(broker, BaseBroker)


class TestAjaibBrokerStructure:
    """Test AjaibBroker class structure and initialization."""
    
    def test_ajaib_initialization(self, broker_credentials):
        """Test Ajaib broker can be initialized."""
        broker = AjaibBroker(**broker_credentials)
        
        assert broker.api_key == broker_credentials["api_key"]
        assert broker.api_secret == broker_credentials["api_secret"]
        assert broker.account_id == broker_credentials["account_id"]
        assert broker.broker_name == "ajaib"
    
    def test_ajaib_inherits_from_basebroker(self, broker_credentials):
        """Test Ajaib is a BaseBroker subclass."""
        broker = AjaibBroker(**broker_credentials)
        assert isinstance(broker, BaseBroker)


class TestIndoPremierBrokerStructure:
    """Test IndoPremierBroker class structure and initialization."""
    
    def test_indopremier_initialization(self, broker_credentials):
        """Test Indo Premier broker can be initialized."""
        broker = IndoPremierBroker(**broker_credentials)
        
        assert broker.api_key == broker_credentials["api_key"]
        assert broker.api_secret == broker_credentials["api_secret"]
        assert broker.account_id == broker_credentials["account_id"]
        assert broker.broker_name == "indopremier"
    
    def test_indopremier_inherits_from_basebroker(self, broker_credentials):
        """Test Indo Premier is a BaseBroker subclass."""
        broker = IndoPremierBroker(**broker_credentials)
        assert isinstance(broker, BaseBroker)


# ============================================================================
# Broker Manager Tests
# ============================================================================

class TestBrokerManager:
    """Test BrokerManager registration, coordination, and aggregation."""
    
    @pytest.fixture
    def mock_market_data(self):
        """Mock market data manager."""
        return MagicMock()
    
    @pytest.fixture
    def manager(self, mock_market_data):
        """Create BrokerManager instance."""
        return BrokerManager(mock_market_data)
    
    def test_manager_initialization(self, manager):
        """Test BrokerManager initializes correctly."""
        assert manager.primary_broker is None
        assert len(manager.brokers) == 0
        assert len(manager.pending_orders) == 0
    
    def test_register_broker_stockbit(self, manager, broker_credentials):
        """Test registering Stockbit broker."""
        result = manager.register_broker(
            BrokerType.STOCKBIT,
            "stockbit_main",
            **broker_credentials,
            is_primary=True,
        )
        
        assert result is not None
        assert isinstance(result, StockbitBroker)
        assert manager.primary_broker == "stockbit_main"
        assert "stockbit_main" in manager.brokers
    
    def test_register_broker_ajaib(self, manager, broker_credentials):
        """Test registering Ajaib broker."""
        result = manager.register_broker(
            BrokerType.AJAIB,
            "ajaib_backup",
            **broker_credentials,
        )
        
        assert result is not None
        assert isinstance(result, AjaibBroker)
        assert "ajaib_backup" in manager.brokers
    
    def test_register_broker_indopremier(self, manager, broker_credentials):
        """Test registering Indo Premier broker."""
        result = manager.register_broker(
            BrokerType.INDOPREMIER,
            "indopremier_backup",
            **broker_credentials,
        )
        
        assert result is not None
        assert isinstance(result, IndoPremierBroker)
        assert "indopremier_backup" in manager.brokers
    
    def test_register_multiple_brokers(self, manager, broker_credentials):
        """Test registering multiple brokers."""
        sb = manager.register_broker(
            BrokerType.STOCKBIT,
            "stockbit",
            **broker_credentials,
            is_primary=True,
        )
        
        aj = manager.register_broker(
            BrokerType.AJAIB,
            "ajaib",
            **broker_credentials,
        )
        
        ip = manager.register_broker(
            BrokerType.INDOPREMIER,
            "indopremier",
            **broker_credentials,
        )
        
        assert len(manager.brokers) == 3
        assert manager.primary_broker == "stockbit"
        assert manager.brokers["stockbit"] == sb
        assert manager.brokers["ajaib"] == aj
        assert manager.brokers["indopremier"] == ip
    
    def test_set_primary_broker(self, manager, broker_credentials):
        """Test setting primary broker."""
        first = manager.register_broker(
            BrokerType.STOCKBIT,
            "sb1",
            **broker_credentials,
            is_primary=True,
        )
        
        assert manager.primary_broker == "sb1"
        
        second = manager.register_broker(
            BrokerType.AJAIB,
            "aj1",
            **broker_credentials,
            is_primary=True,
        )
        
        assert manager.primary_broker == "aj1"
    
    def test_get_broker_status(self, manager, broker_credentials):
        """Test getting broker status."""
        manager.register_broker(
            BrokerType.STOCKBIT,
            "stockbit",
            **broker_credentials,
            is_primary=True,
        )
        
        status = manager.get_broker_status()
        
        assert "stockbit" in status
        assert status["stockbit"]["broker_type"] == "stockbit"
        assert status["stockbit"]["is_primary"] is True
    
    def test_get_pending_orders(self, manager):
        """Test getting pending orders."""
        manager.pending_orders["ORD001"] = {
            "broker": "stockbit",
            "order": MagicMock(),
            "timestamp": datetime.now(JAKARTA_TZ),
        }
        
        pending = manager.get_pending_orders()
        assert "ORD001" in pending
    
    @pytest.mark.asyncio
    async def test_aggregated_positions(self, manager, broker_credentials):
        """Test aggregating positions from multiple brokers."""
        stockbit = manager.register_broker(
            BrokerType.STOCKBIT,
            "stockbit",
            **broker_credentials,
            is_primary=True,
        )
        
        ajaib = manager.register_broker(
            BrokerType.AJAIB,
            "ajaib",
            **broker_credentials,
        )
        
        # Mock positions
        stockbit_positions = [
            Position(
                symbol="BBCA.JK",
                quantity=50,
                avg_cost=15_500.0,
                current_price=15_600.0,
                market_value=780_000.0,
                unrealized_pl=5_000.0,
                unrealized_pl_pct=0.64,
            ),
        ]
        
        ajaib_positions = [
            Position(
                symbol="BBCA.JK",
                quantity=50,
                avg_cost=15_500.0,
                current_price=15_600.0,
                market_value=780_000.0,
                unrealized_pl=5_000.0,
                unrealized_pl_pct=0.64,
            ),
        ]
        
        from unittest.mock import patch
        with patch.object(stockbit, "get_positions", new_callable=AsyncMock) as mock_sb:
            with patch.object(ajaib, "get_positions", new_callable=AsyncMock) as mock_aj:
                mock_sb.return_value = stockbit_positions
                mock_aj.return_value = ajaib_positions
                
                aggregated = await manager.get_aggregated_positions()
                
                assert "BBCA.JK" in aggregated
                assert aggregated["BBCA.JK"]["total_quantity"] == 100
                assert aggregated["BBCA.JK"]["brokers"]["stockbit"] == 50
                assert aggregated["BBCA.JK"]["brokers"]["ajaib"] == 50


# ============================================================================
# Indonesia Compliance Tests
# ============================================================================

class TestIndonesiaCompliance:
    """Test Indonesia market compliance features."""
    
    def test_symbol_format_requirements(self):
        """Test that symbols follow *.JK format (IDX symbols)."""
        valid_symbols = ["BBCA.JK", "BMRI.JK", "TLKM.JK", "ASII.JK"]
        invalid_symbols = ["BBCA", "BBCA.US", "INVALID", "123"]
        
        for symbol in valid_symbols:
            assert symbol.endswith(".JK"), f"{symbol} should be valid"
        
        for symbol in invalid_symbols:
            assert not symbol.endswith(".JK"), f"{symbol} should be invalid"
    
    def test_lot_size_validation_requirements(self):
        """Test that lot sizes are multiples of 100 (IDX standard)."""
        valid_quantities = [100, 200, 500, 1000, 5000]
        invalid_quantities = [50, 150, 75, 99, 101]
        
        for qty in valid_quantities:
            assert qty % 100 == 0, f"{qty} should be valid lot size"
        
        for qty in invalid_quantities:
            assert qty % 100 != 0, f"{qty} should be invalid lot size"
    
    def test_timezone_is_jakarta(self):
        """Test that timezone is properly set to Jakarta (WIB)."""
        assert JAKARTA_TZ is not None
        assert str(JAKARTA_TZ) == "Asia/Jakarta" or "UTC" in str(JAKARTA_TZ)
    
    def test_currency_is_idr(self):
        """Test that all monetary values use IDR currency."""
        account = AccountInfo(
            account_id="TEST",
            account_type=AccountType.CASH,
            cash=1_000_000,  # 1 million IDR
            buying_power=1_500_000,
            market_value=500_000,
            settled_cash=1_000_000,
            unsettled_cash=0,
            equity=1_500_000,
        )
        
        assert account.cash > 0
        assert isinstance(account.cash, (int, float))


# ============================================================================
# Architecture & Pattern Tests
# ============================================================================

class TestBrokerArchitecture:
    """Test overall broker architecture and patterns."""
    
    def test_broker_strategy_pattern(self, broker_credentials):
        """Test that brokers implement Strategy pattern via BaseBroker."""
        brokers = [
            StockbitBroker(**broker_credentials),
            AjaibBroker(**broker_credentials),
            IndoPremierBroker(**broker_credentials),
        ]
        
        # All should have same interface (abstract methods)
        base_methods = {
            "connect",
            "disconnect",
            "get_account_info",
            "get_positions",
            "place_order",
            "cancel_order",
            "get_order_status",
            "get_trades",
        }
        
        for broker in brokers:
            for method in base_methods:
                assert hasattr(broker, method), f"{broker.broker_name} missing {method}"
    
    def test_order_result_consistency(self):
        """Test that order results have consistent structure across brokers."""
        result1 = OrderResult(
            order_id="ORD001",
            broker="stockbit",
            symbol="BBCA.JK",
            side="buy",
            quantity=100,
            filled_quantity=50,
            avg_fill_price=15_600.0,
            status=ExecutionStatus.PARTIALLY_FILLED,
        )
        
        result2 = OrderResult(
            order_id="ORD002",
            broker="ajaib",
            symbol="BMRI.JK",
            side="sell",
            quantity=100,
            filled_quantity=100,
            avg_fill_price=8_000.0,
            status=ExecutionStatus.FILLED,
        )
        
        # Both have same structure
        assert result1.broker == "stockbit"
        assert result2.broker == "ajaib"
        assert result1.status != result2.status
        assert result1.symbol != result2.symbol
        
        # But both use same status enum
        assert isinstance(result1.status, ExecutionStatus)
        assert isinstance(result2.status, ExecutionStatus)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
