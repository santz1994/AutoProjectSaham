import math
from datetime import datetime, timezone
from typing import Any, Optional


class BrokerInterface:
    """Simple broker interface spec."""

    def place_order(
        self, symbol: str, side: str, qty: float, price: float
    ) -> dict[str, Any]:
        raise NotImplementedError()

    def cancel_order(self, order_id: str) -> bool:
        raise NotImplementedError()

    def get_balance(
        self, price_map: Optional[dict[str, float]] = None
    ) -> float:
        raise NotImplementedError()


class PaperBroker(BrokerInterface):
    """A minimal paper trading broker simulator.

    - Maintains cash and fractional position sizes per symbol
    - Executes market orders immediately at provided price
    - Records trades in-memory
    """

    cash: float
    positions: dict[str, float]
    trades: list[dict[str, Any]]

    def __init__(self, cash: float = 10000.0):
        self.cash: float = float(cash)
        self.positions: dict[str, float] = {}
        self.trades: list[dict[str, Any]] = []

    def place_order(self, symbol: str, side: str, qty: float, price: float):
        now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        safe_qty = float(qty)
        if not math.isfinite(safe_qty) or safe_qty <= 0.0:
            trade = {
                "time": now,
                "symbol": symbol,
                "side": side,
                "qty": safe_qty,
                "price": float(price),
                "status": "rejected",
                "reason": "invalid_qty",
            }
            self.trades.append(trade)
            return trade

        # realistic broker fees (approx): buy fee ~0.15%, sell fee ~0.25% (incl. taxes)
        buy_fee_pct = 0.0015
        sell_fee_pct = 0.0025

        if side.lower() == "buy":
            cost = float(price) * safe_qty
            fee = cost * buy_fee_pct
            total_cost = cost + fee
            if total_cost <= self.cash:
                self.cash -= total_cost
                current_pos = float(self.positions.get(symbol, 0.0))
                self.positions[symbol] = current_pos + safe_qty
                trade = {
                    "time": now,
                    "symbol": symbol,
                    "side": "buy",
                    "qty": safe_qty,
                    "price": price,
                    "status": "filled",
                    "fee": float(fee),
                }
                self.trades.append(trade)
                return trade
            else:
                trade = {
                    "time": now,
                    "symbol": symbol,
                    "side": "buy",
                    "qty": safe_qty,
                    "price": price,
                    "status": "rejected",
                    "reason": "insufficient_cash",
                    "required": float(total_cost),
                }
                self.trades.append(trade)
                return trade

        if side.lower() == "sell":
            pos = float(self.positions.get(symbol, 0.0))
            if safe_qty <= pos + 1e-12:
                next_pos = pos - safe_qty
                if abs(next_pos) <= 1e-12:
                    self.positions.pop(symbol, None)
                else:
                    self.positions[symbol] = next_pos
                proceeds = float(price) * safe_qty
                fee = proceeds * sell_fee_pct
                net = proceeds - fee
                self.cash += net
                trade = {
                    "time": now,
                    "symbol": symbol,
                    "side": "sell",
                    "qty": safe_qty,
                    "price": price,
                    "status": "filled",
                    "fee": float(fee),
                    "net": float(net),
                }
                self.trades.append(trade)
                return trade
            else:
                trade = {
                    "time": now,
                    "symbol": symbol,
                    "side": "sell",
                    "qty": safe_qty,
                    "price": price,
                    "status": "rejected",
                    "reason": "insufficient_position",
                }
                self.trades.append(trade)
                return trade

        trade = {
            "time": now,
            "symbol": symbol,
            "side": side,
            "qty": safe_qty,
            "price": price,
            "status": "rejected",
            "reason": "unknown_side",
        }
        self.trades.append(trade)
        return trade

    def cancel_order(self, order_id: str) -> bool:
        # PaperBroker executes immediately; no order queue implemented.
        return False

    def get_balance(
        self, price_map: Optional[dict[str, float]] = None
    ) -> float:
        """Return cash + market value computed with provided price_map.

        price_map: dict symbol -> price
        """
        total = float(self.cash)
        if price_map:
            for sym, qty in self.positions.items():
                last_price = price_map.get(sym)
                if last_price is not None:
                    total += qty * last_price
        return total
