"""PaperBroker adapter that fulfills the BrokerAdapter interface.

This adapter wraps the existing `PaperBroker` simulator so higher-level
execution managers can depend on a common adapter API.
"""
from __future__ import annotations

from typing import Dict, Any, Optional

from .base import BrokerAdapter
from src.execution.executor import PaperBroker


class PaperBrokerAdapter(BrokerAdapter):
    def __init__(self, starting_cash: float = 10000.0):
        # reuse the project's PaperBroker simulator
        self.broker = PaperBroker(cash=starting_cash)
        self._connected = False

    def connect(self) -> bool:
        self._connected = True
        return True

    def place_order(self, symbol: str, side: str, qty: int, price: float) -> Dict[str, Any]:
        return self.broker.place_order(symbol, side, qty, price)

    def cancel_order(self, order_id: str) -> bool:
        return self.broker.cancel_order(order_id)

    def get_positions(self) -> Dict[str, int]:
        return dict(self.broker.positions)

    def get_cash(self) -> float:
        return float(self.broker.cash)

    def get_balance(self, price_map: Optional[Dict[str, float]] = None) -> float:
        return float(self.broker.get_balance(price_map))

    def disconnect(self) -> None:
        self._connected = False
