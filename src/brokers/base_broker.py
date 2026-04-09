"""
Base Broker Interface
=====================

Abstract base class for all broker implementations.
Defines standard interface for trade execution, order management, account operations.

All times: Jakarta timezone (WIB: UTC+7)
All prices: IDR (Rupiah)
Exchange: IDX/IHSG
"""

import asyncio
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Tuple, Any

from src.data.idx_api_client import get_jakarta_now, to_jakarta_time, JAKARTA_TZ


logger = logging.getLogger(__name__)


# ============================================================================
# Enums
# ============================================================================

class ExecutionStatus(Enum):
    """Order execution status."""
    PENDING = "pending"
    ACCEPTED = "accepted"
    PARTIALLY_FILLED = "partially_filled"
    FILLED = "filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"
    FAILED = "failed"


class TimeInForce(Enum):
    """Time in force."""
    DAY = "day"  # Valid only during trading day
    IOC = "ioc"  # Immediate or Cancel
    FOK = "fok"  # Fill or Kill
    GTC = "gtc"  # Good Till Cancelled


class AccountType(Enum):
    """Account type."""
    CASH = "cash"
    MARGIN = "margin"
    DEMO = "demo"


def map_execution_status(
    raw_status: Any,
    aliases: Optional[Dict[str, ExecutionStatus]] = None,
    default: ExecutionStatus = ExecutionStatus.PENDING,
) -> ExecutionStatus:
    """Normalize broker-specific order status strings to ExecutionStatus.

    Broker APIs expose slightly different status values (e.g. "new", "open").
    This helper keeps mapping behavior consistent across all adapters.
    """
    normalized = str(raw_status or "").strip().lower().replace(" ", "_")
    base_map: Dict[str, ExecutionStatus] = {
        "new": ExecutionStatus.PENDING,
        "pending": ExecutionStatus.PENDING,
        "accepted": ExecutionStatus.ACCEPTED,
        "open": ExecutionStatus.ACCEPTED,
        "partially_filled": ExecutionStatus.PARTIALLY_FILLED,
        "partial": ExecutionStatus.PARTIALLY_FILLED,
        "filled": ExecutionStatus.FILLED,
        "cancelled": ExecutionStatus.CANCELLED,
        "canceled": ExecutionStatus.CANCELLED,
        "rejected": ExecutionStatus.REJECTED,
        "failed": ExecutionStatus.FAILED,
    }
    if aliases:
        for key, value in aliases.items():
            alias_key = str(key or "").strip().lower().replace(" ", "_")
            if alias_key:
                base_map[alias_key] = value
    return base_map.get(normalized, default)


# ============================================================================
# Data Classes
# ============================================================================

@dataclass
class AccountInfo:
    """Account information."""
    account_id: str
    account_type: AccountType
    cash: float  # IDR
    buying_power: float  # IDR (available for buying)
    market_value: float  # IDR (current position value)
    settled_cash: float  # IDR (T+2 settled)
    unsettled_cash: float  # IDR (pending settlement)
    equity: float  # IDR (total = cash + market_value)
    day_trades: int = 0
    last_updated: datetime = field(default_factory=get_jakarta_now)
    
    @property
    def total_value(self) -> float:
        """Total account value."""
        return self.equity


@dataclass
class Position:
    """Current position in a symbol."""
    symbol: str
    quantity: int  # Shares
    avg_cost: float  # IDR
    current_price: float  # IDR
    market_value: float  # IDR (quantity * current_price)
    unrealized_pl: float  # IDR
    unrealized_pl_pct: float  # Percentage
    last_updated: datetime = field(default_factory=get_jakarta_now)
    
    @property
    def total_cost(self) -> float:
        """Total cost basis."""
        return self.quantity * self.avg_cost


@dataclass
class OrderResult:
    """Order execution result."""
    order_id: str
    broker: str
    symbol: str
    side: str  # "buy" or "sell"
    quantity: int
    filled_quantity: int
    avg_fill_price: float  # IDR
    status: ExecutionStatus
    timestamp: datetime = field(default_factory=get_jakarta_now)
    fills: List[Dict[str, Any]] = field(default_factory=list)  # Individual fills
    error_message: Optional[str] = None
    
    @property
    def total_value(self) -> float:
        """Total fill value (filled_quantity * avg_fill_price)."""
        return self.filled_quantity * self.avg_fill_price
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class Trade:
    """Completed trade (fill)."""
    trade_id: str
    symbol: str
    side: str  # "buy" or "sell"
    quantity: int
    price: float  # IDR
    timestamp: datetime
    commission: float = 0.0  # IDR
    
    @property
    def total_value(self) -> float:
        return self.quantity * self.price


# ============================================================================
# Base Broker Interface
# ============================================================================

class BaseBroker(ABC):
    """
    Abstract base class for broker implementations.
    
    All subclasses must implement:
    - Authentication
    - Order placement & cancellation
    - Position & account querying
    - Trade history & fills
    """
    
    def __init__(
        self,
        broker_name: str,
        api_key: str,
        api_secret: str,
        account_id: str,
        base_url: str,
        timeout: int = 30,
    ):
        """
        Initialize broker client.
        
        Args:
            broker_name: Broker identifier (e.g., "stockbit", "ajaib")
            api_key: API key for authentication
            api_secret: API secret for authentication
            account_id: Trading account ID
            base_url: API base URL
            timeout: Request timeout in seconds
        """
        self.broker_name = broker_name
        self.api_key = api_key
        self.api_secret = api_secret
        self.account_id = account_id
        self.base_url = base_url
        self.timeout = timeout
        
        self.authenticated = False
        self.session_token: Optional[str] = None
    
    # ========================================================================
    # Authentication
    # ========================================================================
    
    @abstractmethod
    async def connect(self) -> bool:
        """Connect and authenticate with broker."""
        pass
    
    @abstractmethod
    async def disconnect(self) -> bool:
        """Disconnect from broker."""
        pass
    
    # ========================================================================
    # Account & Position Management
    # ========================================================================
    
    @abstractmethod
    async def get_account_info(self) -> Optional[AccountInfo]:
        """Get account information."""
        pass
    
    @abstractmethod
    async def get_positions(self) -> List[Position]:
        """Get all current positions."""
        pass
    
    @abstractmethod
    async def get_position(self, symbol: str) -> Optional[Position]:
        """Get position for specific symbol."""
        pass
    
    # ========================================================================
    # Order Placement & Management
    # ========================================================================
    
    @abstractmethod
    async def place_order(
        self,
        symbol: str,
        quantity: int,
        side: str,  # "buy" or "sell"
        order_type: str = "market",  # "market" or "limit"
        price: Optional[float] = None,  # Required for limit orders
        time_in_force: TimeInForce = TimeInForce.DAY,
    ) -> OrderResult:
        """
        Place an order.
        
        Args:
            symbol: Stock symbol (e.g., "BBCA.JK")
            quantity: Number of shares
            side: "buy" or "sell"
            order_type: "market" or "limit"
            price: Price in IDR (required for limit orders)
            time_in_force: Order validity
        
        Returns:
            OrderResult with execution details
        """
        pass
    
    @abstractmethod
    async def cancel_order(self, order_id: str) -> bool:
        """Cancel a pending order."""
        pass
    
    @abstractmethod
    async def get_order_status(self, order_id: str) -> Optional[OrderResult]:
        """Get status of an order."""
        pass
    
    # ========================================================================
    # Trade History
    # ========================================================================
    
    @abstractmethod
    async def get_trades(
        self,
        symbol: Optional[str] = None,
        limit: int = 100,
    ) -> List[Trade]:
        """Get trade history."""
        pass
    
    # ========================================================================
    # Helpers
    # ========================================================================
    
    def _validate_symbol(self, symbol: str) -> bool:
        """Validate symbol format."""
        return symbol.endswith(".JK")
    
    def _validate_quantity(self, quantity: int) -> bool:
        """Validate quantity (must be multiple of 100)."""
        return quantity > 0 and quantity % 100 == 0
    
    def _validate_side(self, side: str) -> bool:
        """Validate order side."""
        return side.lower() in ["buy", "sell"]

    async def _call_with_retry(
        self,
        operation: str,
        request_fn,
        *,
        max_retries: int = 3,
        initial_delay: float = 0.2,
        backoff: float = 2.0,
    ) -> Any:
        """Execute async request with bounded retries and exponential backoff."""
        retries = max(1, int(max_retries))
        delay = max(0.0, float(initial_delay))
        multiplier = max(1.0, float(backoff))
        last_error: Optional[Exception] = None

        for attempt in range(1, retries + 1):
            try:
                return await request_fn()
            except Exception as exc:  # noqa: PERF203 - explicit retry boundary
                last_error = exc
                if attempt >= retries:
                    break

                logger.warning(
                    "Broker request retry %s attempt %d/%d failed: %s",
                    operation,
                    attempt,
                    retries,
                    exc,
                )
                if delay > 0:
                    await asyncio.sleep(delay)
                delay = delay * multiplier if delay > 0 else 0.0

        if last_error is not None:
            raise last_error
        return None


if __name__ == "__main__":
    print("Base Broker Interface - Ready for implementation")
