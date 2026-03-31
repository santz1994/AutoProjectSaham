"""Abstract broker adapter interface for production adapters."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional


class BrokerAdapter(ABC):
    @abstractmethod
    def connect(self) -> bool:
        raise NotImplementedError()

    @abstractmethod
    def place_order(self, symbol: str, side: str, qty: int, price: float) -> Dict[str, Any]:
        raise NotImplementedError()

    @abstractmethod
    def cancel_order(self, order_id: str) -> bool:
        raise NotImplementedError()

    @abstractmethod
    def get_positions(self) -> Dict[str, int]:
        raise NotImplementedError()

    @abstractmethod
    def get_cash(self) -> float:
        raise NotImplementedError()

    @abstractmethod
    def get_balance(self, price_map: Optional[Dict[str, float]] = None) -> float:
        raise NotImplementedError()

    @abstractmethod
    def disconnect(self) -> None:
        raise NotImplementedError()

    # Optional reconciliation helper: adapters may implement a more detailed
    # `reconcile()` that returns a snapshot of adapter state for reconciliation
    # (positions, cash, balance, trades). This default implementation is a
    # no-op returning an empty dict so callers can call it safely.
    def reconcile(self) -> Dict[str, Any]:
        return {}
