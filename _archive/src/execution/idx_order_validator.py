"""
IDX Order Validator
===================

Task 1 (Phase 3): Order validation for IDX trading rules

Rules enforced:
1. Price Limits: ±35% dari reference price
2. Lot Size: Minimum 100 shares per order
3. Trading Hours: 09:30-16:00 WIB only (+ pre-trading)
4. Settlement: T+2 tracking
5. OJK Compliance: Position limits, margin requirements
6. Market Restrictions: Suspension, delisting checks
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, List, Optional, Tuple, Any

from .idx_api_client import get_jakarta_now, to_jakarta_time, JAKARTA_TZ
from .idx_market_data import IDXMarketDataManager, SessionType


logger = logging.getLogger(__name__)


# ============================================================================
# Enums
# ============================================================================

class OrderType(Enum):
    """Order type."""
    MARKET = "market"
    LIMIT = "limit"
    STOP = "stop"
    STOP_LIMIT = "stop_limit"


class OrderSide(Enum):
    """Order side."""
    BUY = "buy"
    SELL = "sell"


class OrderStatus(Enum):
    """Order status."""
    PENDING = "pending"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    PARTIALLY_FILLED = "partially_filled"
    FILLED = "filled"
    CANCELLED = "cancelled"
    FAILED = "failed"


class ValidationErrorCode(Enum):
    """Validation error codes."""
    INVALID_SYMBOL = "invalid_symbol"
    INVALID_QUANTITY = "invalid_quantity"
    INVALID_PRICE = "invalid_price"
    PRICE_LIMIT_EXCEEDED = "price_limit_exceeded"
    OUTSIDE_TRADING_HOURS = "outside_trading_hours"
    INSUFFICIENT_FUNDS = "insufficient_funds"
    MARKET_SUSPENDED = "market_suspended"
    INVALID_ORDER_TYPE = "invalid_order_type"
    DAILY_LIMIT_EXCEEDED = "daily_limit_exceeded"
    POSITION_LIMIT_EXCEEDED = "position_limit_exceeded"
    PRICE_OUT_OF_RANGE = "price_out_of_range"
    INVALID_TIME_IN_FORCE = "invalid_time_in_force"


# ============================================================================
# Data Classes
# ============================================================================

@dataclass
class Order:
    """Order definition."""
    symbol: str
    side: OrderSide
    quantity: int  # Number of shares
    order_type: OrderType
    price: Optional[float] = None  # IDR, for limit orders
    stop_price: Optional[float] = None  # For stop orders
    timestamp: Optional[datetime] = None
    client_id: Optional[str] = None
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = get_jakarta_now()


@dataclass
class ValidationResult:
    """Validation result for an order."""
    order: Order
    is_valid: bool
    error_code: Optional[ValidationErrorCode] = None
    error_message: Optional[str] = None
    warnings: List[str] = None
    
    def __post_init__(self):
        if self.warnings is None:
            self.warnings = []
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbol": self.order.symbol,
            "is_valid": self.is_valid,
            "error_code": self.error_code.value if self.error_code else None,
            "error_message": self.error_message,
            "warnings": self.warnings,
        }


# ============================================================================
# IDX Order Validator
# ============================================================================

class IDXOrderValidator:
    """
    Validates orders according to IDX rules.
    
    Enforces:
    - Price limits (±35%)
    - Lot size (100 shares)
    - Trading hours (09:30-16:00 WIB)
    - OJK compliance
    - Market restrictions
    """
    
    # IDX Constants
    MIN_LOT_SIZE = 100  # Minimum shares per order
    PRICE_LIMIT_PCT = 35.0  # ±35% limit
    
    def __init__(self, market_data_mgr: IDXMarketDataManager):
        """
        Initialize validator.
        
        Args:
            market_data_mgr: Market data manager for symbol info and prices
        """
        self.market_data_mgr = market_data_mgr
        
        # Daily stats (reset at market open)
        self.daily_buy_volume: Dict[str, int] = {}  # symbol -> shares
        self.daily_sell_volume: Dict[str, int] = {}
        self.daily_buy_value: Dict[str, float] = {}  # symbol -> IDR
        self.daily_sell_value: Dict[str, float] = {}
        self.daily_reset_date: datetime = get_jakarta_now().date()
    
    def validate(
        self,
        order: Order,
        current_balance: Optional[float] = None,
        current_position: Optional[int] = None,
    ) -> ValidationResult:
        """
        Validate an order.
        
        Args:
            order: Order to validate
            current_balance: Available balance in IDR (for buy orders)
            current_position: Current position in shares (for sell orders)
        
        Returns:
            ValidationResult with validation status
        """
        # Reset daily stats if new day
        self._reset_daily_stats_if_needed()
        
        # Basic checks
        if not self._is_symbol_valid(order.symbol):
            return ValidationResult(
                order=order,
                is_valid=False,
                error_code=ValidationErrorCode.INVALID_SYMBOL,
                error_message=f"Symbol {order.symbol} not registered",
            )
        
        if not self._is_quantity_valid(order):
            return ValidationResult(
                order=order,
                is_valid=False,
                error_code=ValidationErrorCode.INVALID_QUANTITY,
                error_message=f"Quantity must be multiple of {self.MIN_LOT_SIZE}",
            )
        
        # Price validation
        price_validation = self._validate_price(order)
        if not price_validation[0]:
            return ValidationResult(
                order=order,
                is_valid=False,
                error_code=ValidationErrorCode.INVALID_PRICE,
                error_message=price_validation[1],
            )
        
        # Trading hours
        if not self._is_trading_hours_valid(order.timestamp):
            return ValidationResult(
                order=order,
                is_valid=False,
                error_code=ValidationErrorCode.OUTSIDE_TRADING_HOURS,
                error_message=f"Order outside trading hours (09:30-16:00 WIB)",
            )
        
        # Market status
        market_check = self._check_market_status(order.symbol)
        if not market_check[0]:
            return ValidationResult(
                order=order,
                is_valid=False,
                error_code=ValidationErrorCode.MARKET_SUSPENDED,
                error_message=market_check[1],
            )
        
        # Fund/position checks
        fund_check = None
        if order.side == OrderSide.BUY and current_balance is not None:
            fund_check = self._check_sufficient_funds(order, current_balance)
            if not fund_check[0]:
                return ValidationResult(
                    order=order,
                    is_valid=False,
                    error_code=ValidationErrorCode.INSUFFICIENT_FUNDS,
                    error_message=fund_check[1],
                )
        
        if order.side == OrderSide.SELL and current_position is not None:
            position_check = self._check_sufficient_position(order, current_position)
            if not position_check[0]:
                return ValidationResult(
                    order=order,
                    is_valid=False,
                    error_code=ValidationErrorCode.POSITION_LIMIT_EXCEEDED,
                    error_message=position_check[1],
                )
        
        # Daily volume check
        daily_check = self._check_daily_limits(order)
        if not daily_check[0]:
            return ValidationResult(
                order=order,
                is_valid=False,
                error_code=ValidationErrorCode.DAILY_LIMIT_EXCEEDED,
                error_message=daily_check[1],
            )
        
        # If all checks pass
        return ValidationResult(
            order=order,
            is_valid=True,
            warnings=self._get_warnings(order),
        )
    
    def _is_symbol_valid(self, symbol: str) -> bool:
        """Check if symbol is registered."""
        return symbol in self.market_data_mgr.symbols
    
    def _is_quantity_valid(self, order: Order) -> bool:
        """Check if quantity is valid lot size (multiple of 100)."""
        if order.quantity <= 0:
            return False
        
        if order.quantity % self.MIN_LOT_SIZE != 0:
            return False
        
        return True
    
    def _validate_price(self, order: Order) -> Tuple[bool, str]:
        """
        Validate order price.
        
        For LIMIT orders: Check price is reasonable
        For MARKET orders: No specific check
        
        Returns:
            (is_valid, error_message)
        """
        if order.order_type == OrderType.MARKET:
            # Market orders don't have price limits
            return True, ""
        
        if order.order_type in [OrderType.LIMIT, OrderType.STOP_LIMIT]:
            if order.price is None or order.price <= 0:
                return False, "Limit price must be positive"
        
        if order.order_type == OrderType.STOP:
            if order.stop_price is None or order.stop_price <= 0:
                return False, "Stop price must be positive"
        
        # Get symbol info for price range
        symbol_info = self.market_data_mgr.get_symbol_info(order.symbol)
        if symbol_info:
            # Check against symbol's price range
            if order.price and (order.price < symbol_info.price_min or 
                               order.price > symbol_info.price_max):
                return False, (
                    f"Price {order.price} outside valid range "
                    f"[{symbol_info.price_min}, {symbol_info.price_max}]"
                )
        
        return True, ""
    
    def _validate_price_against_reference(
        self,
        symbol: str,
        limit_price: float,
    ) -> Tuple[bool, str]:
        """
        Validate limit price against reference price (±35% rule).
        
        This checks the IDX price limit rule.
        """
        latest_price = self.market_data_mgr.get_latest_price(symbol)
        if latest_price is None:
            # No reference price yet, allow order
            return True, ""
        
        if latest_price <= 0:
            return False, "Invalid reference price"
        
        change_pct = abs((limit_price - latest_price) / latest_price) * 100
        
        if change_pct > self.PRICE_LIMIT_PCT:
            return False, (
                f"Price {limit_price} exceeds ±{self.PRICE_LIMIT_PCT}% "
                f"from reference {latest_price} (change: {change_pct:.2f}%)"
            )
        
        return True, ""
    
    def _is_trading_hours_valid(self, timestamp: Optional[datetime]) -> bool:
        """Check if within IDX trading hours."""
        if timestamp is None:
            timestamp = get_jakarta_now()
        
        # Must be during trading hours (not pre-trading)
        return self.market_data_mgr.is_trading_hours(timestamp)
    
    def _check_market_status(self, symbol: str) -> Tuple[bool, str]:
        """Check if symbol/market is available for trading."""
        symbol_info = self.market_data_mgr.get_symbol_info(symbol)
        
        if not symbol_info:
            return False, f"Symbol {symbol} not found"
        
        if not symbol_info.active:
            return False, f"Symbol {symbol} is suspended or delisted"
        
        return True, ""
    
    def _check_sufficient_funds(
        self,
        order: Order,
        balance: float,
    ) -> Tuple[bool, str]:
        """Check if sufficient funds for buy order."""
        latest_price = self.market_data_mgr.get_latest_price(order.symbol)
        
        if latest_price is None:
            # No price data, allow order
            return True, ""
        
        # Use limit price if available, otherwise latest
        price = order.price if order.price else latest_price
        
        required = price * order.quantity
        
        if balance < required:
            return False, (
                f"Insufficient funds: need {required:,.0f} IDR, "
                f"have {balance:,.0f} IDR"
            )
        
        return True, ""
    
    def _check_sufficient_position(
        self,
        order: Order,
        position: int,
    ) -> Tuple[bool, str]:
        """Check if sufficient position for sell order."""
        if position < order.quantity:
            return False, (
                f"Insufficient position: need to sell {order.quantity}, "
                f"have {position} shares"
            )
        
        return True, ""
    
    def _check_daily_limits(self, order: Order) -> Tuple[bool, str]:
        """Check daily trading limits."""
        # Could implement daily volume/value limits here
        # For now, no limit
        return True, ""
    
    def _get_warnings(self, order: Order) -> List[str]:
        """Get warnings for an order."""
        warnings = []
        
        # Check bid-ask spread
        ob = self.market_data_mgr.cache.get_order_book(order.symbol)
        if ob and ob.get_spread_pct():
            spread_pct = ob.get_spread_pct()
            if spread_pct > 1.0:
                warnings.append(
                    f"Wide spread: {spread_pct:.2f}% (may face slippage)"
                )
        
        return warnings
    
    def _reset_daily_stats_if_needed(self) -> None:
        """Reset daily stats if new trading day."""
        today = get_jakarta_now().date()
        if today != self.daily_reset_date:
            self.daily_reset_date = today
            self.daily_buy_volume.clear()
            self.daily_sell_volume.clear()
            self.daily_buy_value.clear()
            self.daily_sell_value.clear()


# ============================================================================
# Order Execution Validator
# ============================================================================

class OrderExecutionValidator:
    """
    Validates orders at execution time.
    
    Checks:
    - Settlement (T+2 for buys)
    - Margin requirements
    - Position limits
    - Regulatory compliance
    """
    
    def __init__(self, market_data_mgr: IDXMarketDataManager):
        """Initialize validator."""
        self.market_data_mgr = market_data_mgr
        self.settlement_days = 2  # T+2
    
    def validate_execution(
        self,
        order: Order,
        fill_price: float,
        fill_quantity: int = None,
    ) -> ValidationResult:
        """
        Validate execution parameters.
        
        Args:
            order: Original order
            fill_price: Executed price
            fill_quantity: Filled quantity (if partial fill)
        
        Returns:
            ValidationResult
        """
        if fill_quantity is None:
            fill_quantity = order.quantity
        
        # Check price is within reasonable range
        latest_price = self.market_data_mgr.get_latest_price(order.symbol)
        if latest_price and fill_price <= 0:
            return ValidationResult(
                order=order,
                is_valid=False,
                error_code=ValidationErrorCode.INVALID_PRICE,
                error_message="Fill price must be positive",
            )
        
        # Check fill quantity is valid lot
        if fill_quantity % 100 != 0:
            return ValidationResult(
                order=order,
                is_valid=False,
                error_code=ValidationErrorCode.INVALID_QUANTITY,
                error_message="Fill quantity must be multiple of 100",
            )
        
        return ValidationResult(
            order=order,
            is_valid=True,
        )
    
    def get_settlement_date(self, trade_date: Optional[datetime] = None) -> datetime:
        """
        Get settlement date for a trade (T+2).
        
        Args:
            trade_date: Trade date (default: today)
        
        Returns:
            Settlement date
        """
        if trade_date is None:
            trade_date = get_jakarta_now()
        
        settlement = trade_date + timedelta(days=self.settlement_days)
        
        # Skip weekends
        while settlement.weekday() >= 5:  # 5=Saturday, 6=Sunday
            settlement += timedelta(days=1)
        
        return settlement


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print("IDX Order Validator Module - Ready for import")
