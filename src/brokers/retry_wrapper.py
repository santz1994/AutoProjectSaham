"""Retry wrapper for BrokerAdapter implementations.

Provides a lightweight wrapper that retries transient failures on
adapter calls (connect, place_order, cancel_order, etc.) with
exponential backoff and optional jitter.

This is useful for networked broker adapters where transient
errors should be retried before failing the execution manager.
"""
from __future__ import annotations

import logging
import random
import time
from typing import Callable, Optional, Tuple

from .base import BrokerAdapter


class RetryBrokerAdapter(BrokerAdapter):
    def __init__(
        self,
        adapter: BrokerAdapter,
        max_retries: int = 3,
        initial_backoff: float = 0.1,
        max_backoff: float = 2.0,
        backoff_multiplier: float = 2.0,
        jitter: float = 0.1,
        logger: Optional[logging.Logger] = None,
        retry_on_exceptions: Tuple[type, ...] = (Exception,),
    ):
        self._adapter = adapter
        self._max_retries = int(max_retries)
        self._initial_backoff = float(initial_backoff)
        self._max_backoff = float(max_backoff)
        self._mult = float(backoff_multiplier)
        self._jitter = float(jitter)
        self._retry_on = retry_on_exceptions
        self._logger = logger or logging.getLogger("autosaham.brokers.retry")

    def _retry_call(self, fn: Callable, *args, **kwargs):
        delay = self._initial_backoff
        last_exc = None
        for attempt in range(1, self._max_retries + 1):
            try:
                return fn(*args, **kwargs)
            except self._retry_on as e:
                last_exc = e
                if attempt == self._max_retries:
                    self._logger.debug(
                        "retry max reached for %s", getattr(fn, "__name__", str(fn))
                    )
                    raise
                # sleep with jitter
                jitter_amt = random.uniform(0, self._jitter * delay)
                sleep_for = min(self._max_backoff, delay) + jitter_amt
                self._logger.debug(
                    "retrying %s after %.3fs (attempt %d/%d): %s",
                    getattr(fn, "__name__", str(fn)),
                    sleep_for,
                    attempt,
                    self._max_retries,
                    e,
                )
                time.sleep(sleep_for)
                delay = min(self._max_backoff, delay * self._mult)

        # if we reach here, re-raise the last exception
        raise last_exc

    # BrokerAdapter interface methods: delegate to underlying adapter with retries
    def connect(self) -> bool:
        return self._retry_call(getattr(self._adapter, "connect"))

    def place_order(self, symbol: str, side: str, qty: int, price: float) -> dict:
        return self._retry_call(
            lambda: self._adapter.place_order(
                symbol,
                side,
                qty,
                price,
            )
        )

    def cancel_order(self, order_id: str) -> bool:
        return self._retry_call(
            lambda: self._adapter.cancel_order(
                order_id,
            )
        )

    def get_positions(self) -> dict:
        return self._retry_call(getattr(self._adapter, "get_positions"))

    def get_cash(self) -> float:
        return float(self._retry_call(getattr(self._adapter, "get_cash")))

    def get_balance(self, price_map: Optional[dict] = None) -> float:
        return float(
            self._retry_call(
                lambda: self._adapter.get_balance(
                    price_map,
                )
            )
        )

    def disconnect(self) -> None:
        try:
            return self._retry_call(getattr(self._adapter, "disconnect"))
        except Exception:
            # best-effort
            self._logger.exception("disconnect failed")

    def reconcile(self) -> dict:
        # reconcile may be heavier; still retry
        if hasattr(self._adapter, "reconcile"):
            return self._retry_call(getattr(self._adapter, "reconcile"))
        return {}

    def reconcile_with_expected(
        self, expected_positions: dict, expected_cash: Optional[float] = None
    ) -> dict:
        if hasattr(self._adapter, "reconcile_with_expected"):
            return self._retry_call(
                lambda: self._adapter.reconcile_with_expected(
                    expected_positions, expected_cash
                )
            )
        # fall back to reconcile
        return self.reconcile()
