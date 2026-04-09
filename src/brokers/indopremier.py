"""
Indo Premier Broker Client
==========================

Implementation for Indo Premier API integration.
Indo Premier is a major Indonesian broker with extensive trading services.

API: https://docs.indopremier.com
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


INDOPREMIER_API_URL = "https://api.indopremier.com/v1"


# ============================================================================
# Indo Premier Broker Client
# ============================================================================

class IndoPremierBroker(BaseBroker):
    """
    Indo Premier broker integration for trade execution.
    
    Features:
    - OAuth2 authentication
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
        Initialize Indo Premier broker.
        
        Args:
            api_key: Indo Premier API key
            api_secret: Indo Premier API secret
            account_id: Trading account ID
            access_token: Optional pre-authorized token
        """
        super().__init__(
            broker_name="indopremier",
            api_key=api_key,
            api_secret=api_secret,
            account_id=account_id,
            base_url=INDOPREMIER_API_URL,
            timeout=30,
        )
        
        self.access_token = access_token
        self.session: Optional[aiohttp.ClientSession] = None
    
    async def connect(self) -> bool:
        """Connect and authenticate with Indo Premier."""
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
            
            logger.info("Connected to Indo Premier")
            return True
        
        except Exception as e:
            logger.error(f"Connection failed: {e}")
            return False
    
    async def disconnect(self) -> bool:
        """Disconnect from Indo Premier."""
        if self.session:
            await self.session.close()
            self.authenticated = False
            logger.info("Disconnected from Indo Premier")
            return True
        return False
    
    async def _authenticate(self) -> Optional[str]:
        """Authenticate and get access token."""
        try:
            auth_url = f"{self.base_url}/authenticate"
            payload = {
                "userID": self.api_key,
                "password": self.api_secret,
            }
            
            async with self.session.post(
                auth_url,
                json=payload,
                timeout=self.timeout,
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    return data.get("sessionID")
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
            "sessionID": self.access_token,
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
                f"indopremier:{method}:{endpoint}",
                _request_once,
            )
        except Exception as e:
            logger.error("Request error: %s", e)
            return None
    
    # ========================================================================
    # Account & Position Management
    # ========================================================================
    
    async def get_account_info(self) -> Optional[AccountInfo]:
        """Get Indo Premier account information."""
        data = await self._make_request("GET", f"/accounts/{self.account_id}")
        
        if not data:
            return None
        
        account = data.get("account", {})
        
        return AccountInfo(
            account_id=self.account_id,
            account_type=AccountType.CASH,
            cash=float(account.get("cash", 0)),
            buying_power=float(account.get("buying_power", 0)),
            market_value=float(account.get("securities_value", 0)),
            settled_cash=float(account.get("settled_cash", 0)),
            unsettled_cash=float(account.get("unsettled_cash", 0)),
            equity=float(account.get("total_equity", 0)),
        )
    
    async def get_positions(self) -> List[Position]:
        """Get all positions from Indo Premier."""
        data = await self._make_request(
            "GET",
            f"/accounts/{self.account_id}/positions",
        )
        
        if not data or "positions" not in data:
            return []
        
        positions = []
        for pos in data["positions"]:
            try:
                position = Position(
                    symbol=pos["symbol"],
                    quantity=int(pos["qty"]),
                    avg_cost=float(pos["avg_price"]),
                    current_price=float(pos["last_price"]),
                    market_value=float(pos["market_value"]),
                    unrealized_pl=float(pos["pl_value"]),
                    unrealized_pl_pct=float(pos["pl_pct"]),
                )
                positions.append(position)
            except (KeyError, ValueError) as e:
                logger.warning(f"Error parsing position: {e}")
        
        return positions
    
    async def get_position(self, symbol: str) -> Optional[Position]:
        """Get position for specific symbol."""
        data = await self._make_request(
            "GET",
            f"/accounts/{self.account_id}/positions/{symbol}",
        )
        
        if not data or "position" not in data:
            return None
        
        pos = data["position"]
        
        return Position(
            symbol=pos["symbol"],
            quantity=int(pos["qty"]),
            avg_cost=float(pos["avg_price"]),
            current_price=float(pos["last_price"]),
            market_value=float(pos["market_value"]),
            unrealized_pl=float(pos["pl_value"]),
            unrealized_pl_pct=float(pos["pl_pct"]),
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
        """Place order on Indo Premier."""
        # Validate inputs
        if not self._validate_symbol(symbol):
            return OrderResult(
                order_id="",
                broker="indopremier",
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
                broker="indopremier",
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
                "code": symbol,
                "side": side.upper(),
                "qty": quantity,
                "type": order_type.upper(),
                "validity": time_in_force.value.upper(),
            }
            
            if order_type.upper() == "LIMIT" and price:
                payload["price"] = price
            
            data = await self._make_request(
                "POST",
                f"/accounts/{self.account_id}/orders",
                json=payload,
            )
            
            if not data or "order" not in data:
                return OrderResult(
                    order_id="",
                    broker="indopremier",
                    symbol=symbol,
                    side=side,
                    quantity=quantity,
                    filled_quantity=0,
                    avg_fill_price=0,
                    status=ExecutionStatus.FAILED,
                    error_message="Order placement failed",
                )
            
            order = data["order"]
            
            status = map_execution_status(order.get("status", "new"))
            
            return OrderResult(
                order_id=order["orderID"],
                broker="indopremier",
                symbol=symbol,
                side=side,
                quantity=quantity,
                filled_quantity=int(order.get("filledQty", 0)),
                avg_fill_price=float(order.get("avgPrice", 0)),
                status=status,
            )
        
        except Exception as e:
            logger.error(f"Order placement error: {e}")
            return OrderResult(
                order_id="",
                broker="indopremier",
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
                f"/accounts/{self.account_id}/orders/{order_id}",
            )
            
            return data is not None and data.get("success", False)
        
        except Exception as e:
            logger.error(f"Cancel error: {e}")
            return False
    
    async def get_order_status(self, order_id: str) -> Optional[OrderResult]:
        """Get order status."""
        try:
            data = await self._make_request(
                "GET",
                f"/accounts/{self.account_id}/orders/{order_id}",
            )
            
            if not data or "order" not in data:
                return None
            
            order = data["order"]
            
            return OrderResult(
                order_id=order_id,
                broker="indopremier",
                symbol=order["code"],
                side=order["side"],
                quantity=int(order["qty"]),
                filled_quantity=int(order.get("filledQty", 0)),
                avg_fill_price=float(order.get("avgPrice", 0)),
                status=map_execution_status(order.get("status", "new")),
            )
        
        except Exception as e:
            logger.error(f"Status check error: {e}")
            return None
    
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
            endpoint = f"/accounts/{self.account_id}/trades?limit={limit}"
            if symbol:
                endpoint += f"&symbol={symbol}"
            
            data = await self._make_request("GET", endpoint)
            
            if not data or "trades" not in data:
                return []
            
            trades = []
            for t in data["trades"]:
                try:
                    trade = Trade(
                        trade_id=t["tradeID"],
                        symbol=t["code"],
                        side=t["side"].lower(),
                        quantity=int(t["qty"]),
                        price=float(t["price"]),
                        timestamp=datetime.fromisoformat(t["executedTime"]),
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
    print("Indo Premier Broker Client - Ready for use")
