"""PaperBroker adapter that fulfills the BrokerAdapter interface.

This adapter wraps the existing `PaperBroker` simulator so higher-level
execution managers can depend on a common adapter API.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from src.execution.executor import PaperBroker

from .base import BrokerAdapter


class PaperBrokerAdapter(BrokerAdapter):
    def __init__(self, starting_cash: float = 10000.0):
        # reuse the project's PaperBroker simulator
        self.broker = PaperBroker(cash=starting_cash)
        self._connected = False

    def connect(self) -> bool:
        self._connected = True
        return True

    def place_order(
        self, symbol: str, side: str, qty: int, price: float
    ) -> Dict[str, Any]:
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

    def reconcile(self) -> Dict[str, Any]:
        """Return a reconciliation snapshot: positions, cash, balance."""
        try:
            return {
                "positions": self.get_positions(),
                "cash": float(self.get_cash()),
                "balance": float(self.get_balance()),
            }
        except Exception:
            return {}

    def reconcile_with_expected(
        self, expected_positions: Dict[str, int], expected_cash: Optional[float] = None
    ) -> Dict[str, Any]:
        """Compare actual state against expected; return a report with diffs."""
        snap = self.reconcile()
        diffs = {}
        actual_pos = snap.get("positions", {})
        for sym, exp_qty in (expected_positions or {}).items():
            act_qty = actual_pos.get(sym, 0)
            if act_qty != exp_qty:
                diffs.setdefault("positions", {})[sym] = {
                    "expected": int(exp_qty),
                    "actual": int(act_qty),
                }

        if expected_cash is not None:
            act_cash = float(snap.get("cash", 0.0))
            if abs(act_cash - float(expected_cash)) > 1e-6:
                diffs["cash"] = {"expected": float(expected_cash), "actual": act_cash}

        return {
            "ok": len(diffs) == 0,
            "diffs": diffs,
            "snapshot": snap,
        }
