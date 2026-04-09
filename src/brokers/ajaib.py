"""
Ajaib Broker Client
===================

Implementation for Ajaib API integration.
Ajaib is an Indonesian equity crowdfunding and trading platform.

API: https://docs.ajaib.co.id
Timezone: Jakarta (WIB: UTC+7)
Currency: IDR
Exchange: IDX
"""

import asyncio
import json
import logging
from datetime import datetime
from typing import Dict, List, Optional, Any

try:
    import aiohttp
    AIOHTTP_AVAILABLE = True
except ImportError:
    AIOHTTP_AVAILABLE = False

from src.data.idx_api_client import get_jakarta_now, JAKARTA_TZ
from .base_broker import (
    BaseBroker, AccountInfo, Position, OrderResult, Trade,
    ExecutionStatus, TimeInForce, AccountType, map_execution_status,
)


logger = logging.getLogger(__name__)


AJAIB_API_URL = "https://api.ajaib.co.id/v1"


# ============================================================================
# Ajaib Broker Client
# ============================================================================

class AjaibBroker(BaseBroker):
    """
    Ajaib broker integration for trade execution.
    
    Features:
    - Bearer token authentication
    - Real-time order management
    - Position tracking
    - Trade history
    - Account balance monitoring
    """
    
    def __init__(
        self,
        api_key: str,
        api_secret: str,
        account_id: str,
        access_token: Optional[str] = None,
    ):
        """
        Initialize Ajaib broker.
        
        Args:
            api_key: Ajaib API key
            api_secret: Ajaib API secret (for auth)
            account_id: Trading account ID
            access_token: Optional pre-authorized token
        """
        super().__init__(
            broker_name="ajaib",
            api_key=api_key,
            api_secret=api_secret,
            account_id=account_id,
            base_url=AJAIB_API_URL,
            timeout=30,
        )
        
        self.access_token = access_token
        self.session: Optional[aiohttp.ClientSession] = None
    
    async def connect(self) -> bool:
        """Connect and authenticate with Ajaib."""
        if not AIOHTTP_AVAILABLE:
            logger.error("aiohttp library not available")
            return False
        
        try:
            self.session = aiohttp.ClientSession()
            
            # Authenticate if no token provided
            if not self.access_token:
                self.access_token = await self._authenticate()
                if not self.access_token:
                    logger.error("Authentication failed")
                    return False
            
            self.authenticated = True
            self.session_token = self.access_token
            
            logger.info("Connected to Ajaib")
            return True
        
        except Exception as e:
            logger.error(f"Connection failed: {e}")
            return False
    
    async def disconnect(self) -> bool:
        """Disconnect from Ajaib."""
        if self.session:
            await self.session.close()
            self.authenticated = False
            logger.info("Disconnected from Ajaib")
            return True
        return False
    
    async def _authenticate(self) -> Optional[str]:
        """Authenticate and get access token."""
        try:
            auth_url = f"{self.base_url}/auth/login"
            payload = {
                "email": self.api_key,
                "password": self.api_secret,
            }
            
            async with self.session.post(
                auth_url,
                json=payload,
                timeout=self.timeout,
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    return data.get("data", {}).get("token")
                else:
                    logger.error(f"Auth failed: {response.status}")
                    return None
        
        except Exception as e:
            logger.error(f"Auth error: {e}")
            return None
    
    async def _make_request(
        self,
        method: str,
        endpoint: str,
        **kwargs,
    ) -> Optional[Dict[str, Any]]:
        """Make authenticated API request."""
        if not self.session:
            logger.error("Request failed: session not initialized")
            return None

        url = f"{self.base_url}{endpoint}"
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }

        async def _request_once() -> Dict[str, Any]:
            async with self.session.request(
                method,
                url,
                headers=headers,
                timeout=self.timeout,
                **kwargs,
            ) as response:
                if response.status in [200, 201]:
                    return await response.json()
                raise RuntimeError(f"HTTP {response.status}")

        try:
            return await self._call_with_retry(
                f"ajaib:{method}:{endpoint}",
                _request_once,
            )
        except Exception as e:
            logger.error("Request error: %s", e)
            return None
    
    # ========================================================================
    # Account & Position Management
    # ========================================================================
    
    async def get_account_info(self) -> Optional[AccountInfo]:
        """Get Ajaib account information."""
        data = await self._make_request("GET", "/users/portfolio")
        
        if not data:
            return None
        
        portfolio = data.get("data", {})
        
        return AccountInfo(
            account_id=self.account_id,
            account_type=AccountType.CASH,
            cash=float(portfolio.get("cash", 0)),
            buying_power=float(portfolio.get("buying_power", 0)),
            market_value=float(portfolio.get("portfolio_value", 0)),
            settled_cash=float(portfolio.get("cash", 0)),
            unsettled_cash=0,
            equity=float(portfolio.get("total_value", 0)),
        )
    
    async def get_positions(self) -> List[Position]:
        """Get all positions from Ajaib."""
        data = await self._make_request("GET", "/users/portfolio/stocks")
        
        if not data or "data" not in data:
            return []
        
        positions = []
        for pos in data["data"]:
            try:
                position = Position(
                    symbol=pos["symbol"],
                    quantity=int(pos["quantity"]),
                    avg_cost=float(pos["avg_cost"]),
                    current_price=float(pos["last_price"]),
                    market_value=float(pos["market_value"]),
                    unrealized_pl=float(pos["gain_loss"]),
                    unrealized_pl_pct=float(pos["gain_loss_pct"]),
                )
                positions.append(position)
            except (KeyError, ValueError) as e:
                logger.warning(f"Error parsing position: {e}")
        
        return positions
    
    async def get_position(self, symbol: str) -> Optional[Position]:
        """Get position for specific symbol."""
        data = await self._make_request(
            "GET",
            f"/users/portfolio/stocks/{symbol}",
        )
        
        if not data or "data" not in data:
            return None
        
        pos = data["data"]
        
        return Position(
            symbol=pos["symbol"],
            quantity=int(pos["quantity"]),
            avg_cost=float(pos["avg_cost"]),
            current_price=float(pos["last_price"]),
            market_value=float(pos["market_value"]),
            unrealized_pl=float(pos["gain_loss"]),
            unrealized_pl_pct=float(pos["gain_loss_pct"]),
        )
    
    # ========================================================================
    # Order Management
    # ========================================================================
    
    async def place_order(
        self,
        symbol: str,
        quantity: int,
        side: str,
        order_type: str = "market",
        price: Optional[float] = None,
        time_in_force: TimeInForce = TimeInForce.DAY,
    ) -> OrderResult:
        """Place order on Ajaib."""
        # Validate inputs
        if not self._validate_symbol(symbol):
            return OrderResult(
                order_id="",
                broker="ajaib",
                symbol=symbol,
                side=side,
                quantity=quantity,
                filled_quantity=0,
                avg_fill_price=0,
                status=ExecutionStatus.REJECTED,
                error_message=f"Invalid symbol: {symbol}",
            )
        
        if not self._validate_quantity(quantity):
            return OrderResult(
                order_id="",
                broker="ajaib",
                symbol=symbol,
                side=side,
                quantity=quantity,
                filled_quantity=0,
                avg_fill_price=0,
                status=ExecutionStatus.REJECTED,
                error_message=f"Invalid quantity: {quantity}",
            )
        
        try:
            payload = {
                "symbol": symbol,
                "quantity": quantity,
                "side": side.upper(),  # Ajaib uses uppercase
                "type": order_type.upper(),
                "time_in_force": time_in_force.value.upper(),
            }
            
            if order_type.upper() == "LIMIT" and price:
                payload["price"] = price
            
            data = await self._make_request(
                "POST",
                "/orders",
                json=payload,
            )
            
            if not data or "data" not in data:
                return OrderResult(
                    order_id="",
                    broker="ajaib",
                    symbol=symbol,
                    side=side,
                    quantity=quantity,
                    filled_quantity=0,
                    avg_fill_price=0,
                    status=ExecutionStatus.FAILED,
                    error_message="Order placement failed",
                )
            
            order = data["data"]
            
            status = map_execution_status(order.get("status", "pending"))
            
            return OrderResult(
                order_id=order["id"],
                broker="ajaib",
                symbol=symbol,
                side=side,
                quantity=quantity,
                filled_quantity=int(order.get("filled_quantity", 0)),
                avg_fill_price=float(order.get("avg_fill_price", 0)),
                status=status,
            )
        
        except Exception as e:
            logger.error(f"Order placement error: {e}")
            return OrderResult(
                order_id="",
                broker="ajaib",
                symbol=symbol,
                side=side,
                quantity=quantity,
                filled_quantity=0,
                avg_fill_price=0,
                status=ExecutionStatus.FAILED,
                error_message=str(e),
            )
    
    async def cancel_order(self, order_id: str) -> bool:
        """Cancel a pending order."""
        try:
            data = await self._make_request(
                "DELETE",
                f"/orders/{order_id}",
            )
            
            return data is not None
        
        except Exception as e:
            logger.error(f"Cancel error: {e}")
            return False
    
    async def get_order_status(self, order_id: str) -> Optional[OrderResult]:
        """Get order status."""
        try:
            data = await self._make_request(
                "GET",
                f"/orders/{order_id}",
            )
            
            if not data or "data" not in data:
                return None
            
            order = data["data"]
            
            return OrderResult(
                order_id=order_id,
                broker="ajaib",
                symbol=order["symbol"],
                side=order["side"],
                quantity=int(order["quantity"]),
                filled_quantity=int(order.get("filled_quantity", 0)),
                avg_fill_price=float(order.get("avg_fill_price", 0)),
                status=map_execution_status(order.get("status", "pending")),
            )
        
        except Exception as e:
            logger.error(f"Status check error: {e}")
            return None

    async def list_open_orders(self, limit: int = 200) -> List[str]:
        """List open order ids for best-effort mass cancellation."""
        safe_limit = max(1, min(1000, int(limit)))

        try:
            data = await self._make_request(
                "GET",
                f"/orders?status=open&limit={safe_limit}",
            )
            if not data:
                return []

            items = data.get("data")
            if not isinstance(items, list):
                return []

            order_ids: List[str] = []
            for item in items:
                if not isinstance(item, dict):
                    continue
                status = map_execution_status(item.get("status", "pending"))
                if status not in {
                    ExecutionStatus.PENDING,
                    ExecutionStatus.ACCEPTED,
                    ExecutionStatus.PARTIALLY_FILLED,
                }:
                    continue

                order_id = str(item.get("id") or item.get("order_id") or "").strip()
                if order_id:
                    order_ids.append(order_id)

            return order_ids[:safe_limit]
        except Exception as e:
            logger.error(f"Open-order query error: {e}")
            return []
    
    # ========================================================================
    # Trade History
    # ========================================================================
    
    async def get_trades(
        self,
        symbol: Optional[str] = None,
        limit: int = 100,
    ) -> List[Trade]:
        """Get trade history."""
        try:
            endpoint = f"/users/trades?limit={limit}"
            if symbol:
                endpoint += f"&symbol={symbol}"
            
            data = await self._make_request("GET", endpoint)
            
            if not data or "data" not in data:
                return []
            
            trades = []
            for t in data["data"]:
                try:
                    trade = Trade(
                        trade_id=t["id"],
                        symbol=t["symbol"],
                        side=t["side"].lower(),
                        quantity=int(t["quantity"]),
                        price=float(t["price"]),
                        timestamp=datetime.fromisoformat(t["executed_at"]),
                        commission=float(t.get("commission", 0)),
                    )
                    trades.append(trade)
                except (KeyError, ValueError) as e:
                    logger.warning(f"Error parsing trade: {e}")
            
            return trades
        
        except Exception as e:
            logger.error(f"Trade history error: {e}")
            return []


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print("Ajaib Broker Client - Ready for use")
