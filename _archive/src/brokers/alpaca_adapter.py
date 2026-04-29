"""Alpaca broker adapter stub.

This adapter is a best-effort wrapper that will use `alpaca_trade_api` if
installed and credentials are available via environment or `.env` using
`src.utils.secrets.SecretsManager`. It intentionally falls back to a
no-op/rejected behavior when the third-party SDK is not installed, so the
repository remains runnable without that dependency.
"""
from __future__ import annotations

import logging
import uuid
from typing import Any, Dict, Optional

from src.brokers.paper_adapter import PaperBrokerAdapter
from src.utils.secrets import SecretsManager

from .base import BrokerAdapter

log = logging.getLogger("autosaham.brokers.alpaca")


class AlpacaAdapter(BrokerAdapter):
    def __init__(
        self,
        api_key: Optional[str] = None,
        api_secret: Optional[str] = None,
        base_url: Optional[str] = None,
    ):
        sm = SecretsManager()
        self.api_key = api_key or sm.get("ALPACA_API_KEY")
        self.api_secret = api_secret or sm.get("ALPACA_API_SECRET")
        self.base_url = (
            base_url or sm.get("ALPACA_BASE_URL") or "https://paper-api.alpaca.markets"
        )
        self.client = None
        self.max_retries = 3
        self.retry_backoff = 0.5
        # simulator fallback for local testing when Alpaca SDK is not present
        self.simulator = PaperBrokerAdapter(
            starting_cash=float(sm.get("SIM_STARTING_CASH") or 10000.0)
        )
        # local order registry for simulator and mapping to remote ids
        self._sim_orders: dict[str, dict] = {}
        self._remote_map: dict[str, str] = {}
        # SECURITY FIX: Track submitted orders by idempotency key to prevent duplicate orders
        self._order_idempotency_map: dict[str, dict] = {}  # idempotency_key -> order result

    def connect(self) -> bool:
        try:
            import alpaca_trade_api as tradeapi

            self.client = tradeapi.REST(
                self.api_key,
                self.api_secret,
                base_url=self.base_url,
            )
            # quick sanity check
            try:
                _ = self.client.get_account()
            except Exception:
                log.exception("Alpaca client created but get_account failed")
            return True
        except Exception:
            log.warning(
                "alpaca_trade_api not installed or failed to init; running in stub mode"
            )
            self.client = None
            return False

    def _with_retries(self, fn, *args, **kwargs):
        """Simple retry wrapper with exponential backoff."""
        last_exc = None
        for attempt in range(1, self.max_retries + 1):
            try:
                return fn(*args, **kwargs)
            except Exception as e:
                last_exc = e
                wait = self.retry_backoff * (2 ** (attempt - 1))
                log.warning(
                    "alpaca call failed (attempt %d/%d): %s; retrying in %.2fs",
                    attempt,
                    self.max_retries,
                    e,
                    wait,
                )
                try:
                    import time

                    time.sleep(wait)
                except Exception:
                    pass
        log.exception("alpaca call ultimately failed after retries: %s", last_exc)
        raise last_exc

    def place_order(
        self, symbol: str, side: str, qty: int, price: float
    ) -> Dict[str, Any]:
        # SECURITY FIX: Generate and check idempotency key to prevent duplicate orders
        # Idempotency key = hash(symbol, side, qty, price) ensures same order isn't placed twice
        from hashlib import sha256
        idempotency_key = sha256(f"{symbol}:{side}:{qty}:{price}:{int(__import__('time').time())//60}".encode()).hexdigest()[:16]
        
        # Check if this order was already submitted
        if idempotency_key in self._order_idempotency_map:
            log.info(f"Order already submitted with key {idempotency_key}; returning cached result")
            return self._order_idempotency_map[idempotency_key]
        
        # If Alpaca SDK not available, use local simulator and return a mapped order
        if self.client is None:
            trade = self.simulator.place_order(symbol, side, qty, price)
            oid = f"sim-{uuid.uuid4().hex}"
            self._sim_orders[oid] = trade
            result = {
                "status": trade.get("status"),
                "order_id": oid,
                "raw": trade,
                "idempotency_key": idempotency_key,
            }
            self._order_idempotency_map[idempotency_key] = result
            return result

        try:

            def _submit():
                if side.lower() == "buy":
                    return self.client.submit_order(
                        symbol, qty, side="buy", type="market", time_in_force="day"
                    )
                else:
                    return self.client.submit_order(
                        symbol, qty, side="sell", type="market", time_in_force="day"
                    )

            order = self._with_retries(_submit)
            # map known status strings (best-effort)
            status = getattr(order, "status", None)
            raw = getattr(order, "_raw", None) or {}
            if status is None and isinstance(raw, dict):
                status = raw.get("status")

            # attempt to fetch order id
            remote_id = getattr(order, "id", None) or raw.get("id")
            local_id = f"rem-{uuid.uuid4().hex}"
            if remote_id:
                self._remote_map[local_id] = remote_id

            mapped_status = "submitted"
            if isinstance(status, str) and status.lower() in ("filled", "closed"):
                mapped_status = "filled"
            elif isinstance(status, str) and status.lower() in (
                "canceled",
                "cancelled",
                "rejected",
            ):
                mapped_status = "rejected"

            result = {
                "status": mapped_status,
                "order_id": local_id,
                "remote_id": remote_id,
                "raw": raw,
                "idempotency_key": idempotency_key,
            }
            self._order_idempotency_map[idempotency_key] = result
            return result
        except Exception:
            log.exception("failed to place order via Alpaca")
            return {"status": "rejected", "reason": "alpaca_place_failed"}

    def get_order_status(self, order_id: str) -> Dict[str, Any]:
        """Return a standardized order status dict for a local order id.

        Looks up simulator orders or remote orders mapped in `_remote_map`.
        """
        # simulator
        if order_id in self._sim_orders:
            return {
                "status": self._sim_orders[order_id].get("status"),
                "raw": self._sim_orders[order_id],
            }

        # remote
        remote_id = self._remote_map.get(order_id)
        if self.client is None:
            return {"status": "unknown", "raw": None}
        try:
            order = self._with_retries(lambda: self.client.get_order(remote_id))
            status = getattr(order, "status", None)
            raw = getattr(order, "_raw", None) or {}
            return {"status": status, "raw": raw}
        except Exception:
            log.exception("get_order_status failed")
            return {"status": "error", "raw": None}

    def list_orders(self) -> Dict[str, Any]:
        """Return list of recent orders (simulator + remote mapping)."""
        out = {}
        out.update({k: v for k, v in self._sim_orders.items()})
        if self.client is not None:
            try:
                remote = self._with_retries(lambda: self.client.list_orders())
                out["remote_count"] = len(remote)
            except Exception:
                log.exception("list_orders failed")
        return out

    def cancel_order(self, order_id: str) -> bool:
        if self.client is None:
            return False
        try:
            self.client.cancel_order(order_id)
            return True
        except Exception:
            log.exception("cancel_order failed")
            return False

    def get_positions(self) -> Dict[str, int]:
        if self.client is None:
            return {}
        try:
            pos_list = self.client.list_positions()
            return {p.symbol: int(p.qty) for p in pos_list}
        except Exception:
            log.exception("failed to fetch positions")
            return {}

    def get_cash(self) -> float:
        if self.client is None:
            return 0.0
        try:
            account = self.client.get_account()
            return float(account.cash)
        except Exception:
            log.exception("failed to fetch account cash")
            return 0.0

    def get_balance(self, price_map: Optional[Dict[str, float]] = None) -> float:
        # best-effort: cash + positions * price_map
        cash = self.get_cash()
        positions = self.get_positions()
        total = cash
        if price_map:
            for s, q in positions.items():
                p = price_map.get(s)
                if p is not None:
                    total += q * p
        return float(total)

    def disconnect(self) -> None:
        self.client = None
