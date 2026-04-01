"""
Broker Integration Manager
===========================

Unified interface for managing multiple broker connections and trade execution.
Handles broker selection, order routing, position aggregation, and account management.

Timezone: Jakarta (WIB: UTC+7)
Currency: IDR
Exchange: IDX
"""

import asyncio
import logging
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Any

from src.data.idx_api_client import get_jakarta_now, JAKARTA_TZ
from src.data.idx_market_data import IDXMarketDataManager

from .base_broker import (
    BaseBroker, AccountInfo, Position, OrderResult, Trade,
    ExecutionStatus, TimeInForce,
)
from .stockbit import StockbitBroker
from .ajaib import AjaibBroker
from .indopremier import IndoPremierBroker


logger = logging.getLogger(__name__)


class BrokerType(Enum):
    """Supported brokers."""
    STOCKBIT = "stockbit"
    AJAIB = "ajaib"
    INDOPREMIER = "indopremier"


# ============================================================================
# Broker Manager
# ============================================================================

class BrokerManager:
    """
    Manages multiple broker connections and provides unified trading interface.
    
    Features:
    - Multi-broker support
    - Order routing and execution
    - Position aggregation
    - Account management
    - Trade history tracking
    - Real-time sync with market data
    """
    
    def __init__(self, market_data_mgr: IDXMarketDataManager):
        """
        Initialize broker manager.
        
        Args:
            market_data_mgr: Market data manager for price validation
        """
        self.market_data_mgr = market_data_mgr
        self.brokers: Dict[str, BaseBroker] = {}
        self.primary_broker: Optional[str] = None
        self.pending_orders: Dict[str, Dict[str, Any]] = {}  # order_id -> order info
    
    def register_broker(
        self,
        broker_type: BrokerType,
        name: str,
        api_key: str,
        api_secret: str,
        account_id: str,
        is_primary: bool = False,
    ) -> Optional[BaseBroker]:
        """
        Register a broker connection.
        
        Args:
            broker_type: Broker type (Stockbit, Ajaib, Indo Premier)
            name: Connection name (e.g., "stockbit_main", "ajaib_backup")
            api_key: API key for authentication
            api_secret: API secret for authentication
            account_id: Trading account ID
            is_primary: Set as primary broker for routing
        
        Returns:
            Broker instance or None if failed
        """
        try:
            broker: Optional[BaseBroker] = None
            
            if broker_type == BrokerType.STOCKBIT:
                broker = StockbitBroker(
                    api_key=api_key,
                    api_secret=api_secret,
                    account_id=account_id,
                )
            elif broker_type == BrokerType.AJAIB:
                broker = AjaibBroker(
                    api_key=api_key,
                    api_secret=api_secret,
                    account_id=account_id,
                )
            elif broker_type == BrokerType.INDOPREMIER:
                broker = IndoPremierBroker(
                    api_key=api_key,
                    api_secret=api_secret,
                    account_id=account_id,
                )
            
            if broker:
                self.brokers[name] = broker
                
                if is_primary or self.primary_broker is None:
                    self.primary_broker = name
                    logger.info(f"Set primary broker: {name}")
                
                logger.info(f"Registered broker: {name} ({broker_type.value})")
                return broker
        
        except Exception as e:
            logger.error(f"Broker registration failed: {e}")
        
        return None
    
    async def connect_all(self) -> bool:
        """Connect all registered brokers."""
        results = []
        for name, broker in self.brokers.items():
            try:
                result = await broker.connect()
                results.append((name, result))
                logger.info(f"Broker {name}: {'Connected' if result else 'Failed'}")
            except Exception as e:
                logger.error(f"Broker {name} connection error: {e}")
                results.append((name, False))
        
        return all(r[1] for r in results)
    
    async def disconnect_all(self) -> bool:
        """Disconnect all brokers."""
        results = []
        for name, broker in self.brokers.items():
            try:
                result = await broker.disconnect()
                results.append((name, result))
            except Exception as e:
                logger.error(f"Broker {name} disconnection error: {e}")
                results.append((name, False))
        
        return all(r[1] for r in results)
    
    # ========================================================================
    # Account & Position Management
    # ========================================================================
    
    async def get_account_info(self, broker_name: Optional[str] = None) -> Optional[AccountInfo]:
        """Get account info from primary or specified broker."""
        name = broker_name or self.primary_broker
        if not name or name not in self.brokers:
            logger.warning(f"Broker {name} not found")
            return None
        
        return await self.brokers[name].get_account_info()
    
    async def get_accounts_info(self) -> Dict[str, Optional[AccountInfo]]:
        """Get account info from all brokers."""
        accounts = {}
        for name, broker in self.brokers.items():
            try:
                accounts[name] = await broker.get_account_info()
            except Exception as e:
                logger.error(f"Error getting account info from {name}: {e}")
                accounts[name] = None
        
        return accounts
    
    async def get_total_equity(self) -> float:
        """Get total equity across all brokers."""
        total = 0.0
        accounts = await self.get_accounts_info()
        
        for account in accounts.values():
            if account:
                total += account.equity
        
        return total
    
    async def get_positions(self, broker_name: Optional[str] = None) -> List[Position]:
        """Get positions from primary or specified broker."""
        name = broker_name or self.primary_broker
        if not name or name not in self.brokers:
            return []
        
        try:
            return await self.brokers[name].get_positions()
        except Exception as e:
            logger.error(f"Error getting positions from {name}: {e}")
            return []
    
    async def get_all_positions(self) -> Dict[str, List[Position]]:
        """Get positions from all brokers and aggregate."""
        positions = {}
        
        for name, broker in self.brokers.items():
            try:
                positions[name] = await broker.get_positions()
            except Exception as e:
                logger.error(f"Error getting positions from {name}: {e}")
                positions[name] = []
        
        return positions
    
    async def get_aggregated_positions(self) -> Dict[str, Dict[str, Any]]:
        """
        Get aggregated position data across all brokers.
        
        Returns dict of:
        {
            "BBCA.JK": {
                "total_quantity": 100,
                "brokers": {"stockbit": 50, "ajaib": 50},
                "avg_cost": 15500.0,
                "current_price": 15600.0,
                "market_value": 1560000.0,
            }
        }
        """
        all_positions = await self.get_all_positions()
        aggregated = {}
        
        for broker_name, positions in all_positions.items():
            for position in positions:
                symbol = position.symbol
                
                if symbol not in aggregated:
                    aggregated[symbol] = {
                        "total_quantity": 0,
                        "total_cost": 0,
                        "brokers": {},
                        "current_price": position.current_price,
                        "market_value": 0,
                    }
                
                aggregated[symbol]["total_quantity"] += position.quantity
                aggregated[symbol]["total_cost"] += position.total_cost
                aggregated[symbol]["brokers"][broker_name] = position.quantity
                aggregated[symbol]["current_price"] = position.current_price
        
        # Calculate aggregate metrics
        for symbol, data in aggregated.items():
            if data["total_quantity"] > 0:
                data["avg_cost"] = data["total_cost"] / data["total_quantity"]
                data["market_value"] = (
                    data["total_quantity"] * data["current_price"]
                )
        
        return aggregated
    
    # ========================================================================
    # Order Placement & Management
    # ========================================================================
    
    async def place_order(
        self,
        symbol: str,
        quantity: int,
        side: str,
        order_type: str = "market",
        price: Optional[float] = None,
        broker_name: Optional[str] = None,
        time_in_force: TimeInForce = TimeInForce.DAY,
    ) -> OrderResult:
        """
        Place order on primary or specified broker.
        
        Args:
            symbol: Stock symbol
            quantity: Number of shares
            side: "buy" or "sell"
            order_type: "market" or "limit"
            price: Price in IDR (required for limit orders)
            broker_name: Broker to use (default: primary)
            time_in_force: Order validity
        
        Returns:
            OrderResult with execution details
        """
        name = broker_name or self.primary_broker
        if not name or name not in self.brokers:
            return OrderResult(
                order_id="",
                broker="unknown",
                symbol=symbol,
                side=side,
                quantity=quantity,
                filled_quantity=0,
                avg_fill_price=0,
                status=ExecutionStatus.REJECTED,
                error_message=f"Broker {name} not found",
            )
        
        try:
            result = await self.brokers[name].place_order(
                symbol=symbol,
                quantity=quantity,
                side=side,
                order_type=order_type,
                price=price,
                time_in_force=time_in_force,
            )
            
            # Store pending order
            if result.order_id:
                self.pending_orders[result.order_id] = {
                    "broker": name,
                    "order": result,
                    "timestamp": get_jakarta_now(),
                }
            
            return result
        
        except Exception as e:
            logger.error(f"Order placement error: {e}")
            return OrderResult(
                order_id="",
                broker=name,
                symbol=symbol,
                side=side,
                quantity=quantity,
                filled_quantity=0,
                avg_fill_price=0,
                status=ExecutionStatus.FAILED,
                error_message=str(e),
            )
    
    async def cancel_order(self, order_id: str, broker_name: Optional[str] = None) -> bool:
        """Cancel an order."""
        name = broker_name
        
        # Try to find broker from pending orders if not specified
        if not name and order_id in self.pending_orders:
            name = self.pending_orders[order_id]["broker"]
        
        if not name or name not in self.brokers:
            logger.warning(f"Broker {name} not found for order {order_id}")
            return False
        
        try:
            result = await self.brokers[name].cancel_order(order_id)
            
            if result and order_id in self.pending_orders:
                del self.pending_orders[order_id]
            
            return result
        
        except Exception as e:
            logger.error(f"Cancel error: {e}")
            return False
    
    async def get_order_status(self, order_id: str, broker_name: Optional[str] = None) -> Optional[OrderResult]:
        """Get order status."""
        name = broker_name
        
        if not name and order_id in self.pending_orders:
            name = self.pending_orders[order_id]["broker"]
        
        if not name or name not in self.brokers:
            return None
        
        try:
            return await self.brokers[name].get_order_status(order_id)
        except Exception as e:
            logger.error(f"Status check error: {e}")
            return None
    
    # ========================================================================
    # Trade History
    # ========================================================================
    
    async def get_trades(
        self,
        symbol: Optional[str] = None,
        broker_name: Optional[str] = None,
        limit: int = 100,
    ) -> List[Trade]:
        """Get trades from specified broker."""
        name = broker_name or self.primary_broker
        if not name or name not in self.brokers:
            return []
        
        try:
            return await self.brokers[name].get_trades(symbol=symbol, limit=limit)
        except Exception as e:
            logger.error(f"Trade history error: {e}")
            return []
    
    async def get_all_trades(
        self,
        symbol: Optional[str] = None,
        limit: int = 100,
    ) -> Dict[str, List[Trade]]:
        """Get trades from all brokers."""
        trades = {}
        
        for name, broker in self.brokers.items():
            try:
                trades[name] = await broker.get_trades(symbol=symbol, limit=limit)
            except Exception as e:
                logger.error(f"Trade history error from {name}: {e}")
                trades[name] = []
        
        return trades
    
    # ========================================================================
    # Status & Monitoring
    # ========================================================================
    
    def get_broker_status(self) -> Dict[str, Dict[str, Any]]:
        """Get status of all connected brokers."""
        status = {}
        
        for name, broker in self.brokers.items():
            status[name] = {
                "broker_type": broker.broker_name,
                "authenticated": broker.authenticated,
                "is_primary": (name == self.primary_broker),
            }
        
        return status
    
    def get_pending_orders(self) -> Dict[str, Dict[str, Any]]:
        """Get all pending orders."""
        return self.pending_orders.copy()
    
    async def sync_pending_orders(self) -> int:
        """
        Check status of all pending orders and remove completed ones.
        
        Returns:
            Number of orders still pending
        """
        to_remove = []
        
        for order_id, order_info in self.pending_orders.items():
            status = await self.get_order_status(
                order_id,
                order_info["broker"],
            )
            
            if status and status.status in [
                ExecutionStatus.FILLED,
                ExecutionStatus.CANCELLED,
                ExecutionStatus.REJECTED,
                ExecutionStatus.FAILED,
            ]:
                to_remove.append(order_id)
        
        for order_id in to_remove:
            del self.pending_orders[order_id]
        
        return len(self.pending_orders)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print("Broker Manager - Ready for use")
