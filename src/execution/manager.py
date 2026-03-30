"""Execution manager wrapping a broker adapter and enforcing pre-trade risk checks.

This manager accepts either the project's `PaperBroker` or any adapter
implementing the `BrokerAdapter` interface (see `src.brokers.base`). It
adds optional alert callbacks and logging while maintaining backward
compatibility with existing code.
"""
from __future__ import annotations

import logging
from typing import Optional, Callable, Any

from .idx_rules import calculate_idx_limits

try:
    # optional import; available when broker adapters added
    from src.brokers.base import BrokerAdapter
except Exception:
    BrokerAdapter = None  # type: ignore


class ExecutionManager:
    def __init__(self, broker: Optional[Any] = None, max_position_per_symbol: int = 1000, max_total_notional: float = 1e9, daily_loss_limit: float = 0.05, alert_callback: Optional[Callable[[dict], None]] = None, logger: Optional[logging.Logger] = None):
        # keep backward compat: broker may be a PaperBroker instance
        self.broker = broker
        self.max_position_per_symbol = int(max_position_per_symbol)
        self.max_total_notional = float(max_total_notional)
        self.daily_loss_limit = float(daily_loss_limit)
        self._start_balance = None
        self._frozen = False
        self._frozen_reason = None
        self.alert_callback = alert_callback
        self.logger = logger or logging.getLogger('autosaham.execution')

        # lazily create a default paper broker if none provided
        if self.broker is None:
            try:
                from .executor import PaperBroker

                self.broker = PaperBroker()
            except Exception:
                self.broker = None

    # --- broker compatibility helpers ---
    def _get_positions(self) -> dict:
        if self.broker is None:
            return {}
        if hasattr(self.broker, 'positions'):
            return getattr(self.broker, 'positions')
        if hasattr(self.broker, 'get_positions'):
            return self.broker.get_positions()
        return {}

    def _get_balance(self, price_map: dict | None = None) -> float:
        price_map = price_map or {}
        if self.broker is None:
            return 0.0
        if hasattr(self.broker, 'get_balance'):
            return float(self.broker.get_balance(price_map))
        # fallback: compute from `cash` and `positions` attributes if present
        cash = float(getattr(self.broker, 'cash', 0.0))
        positions = self._get_positions()
        total = cash
        for sym, qty in positions.items():
            last = price_map.get(sym)
            if last is not None:
                total += qty * last
        return float(total)

    def _place(self, symbol: str, side: str, qty: int, price: float) -> dict:
        if self.broker is None:
            return {'status': 'rejected', 'reason': 'no_broker'}
        # adapter or raw broker should expose place_order
        if hasattr(self.broker, 'place_order'):
            return self.broker.place_order(symbol, side, qty, price)
        return {'status': 'rejected', 'reason': 'broker_missing_place_order'}

    def _alert(self, ev: dict) -> None:
        try:
            if self.alert_callback:
                self.alert_callback(ev)
        except Exception:
            self.logger.exception('alert callback failed')

    # --- public methods ---
    def start_day(self, price_map: dict | None = None):
        # record starting balance for the day
        self._start_balance = self._get_balance(price_map or {})
        self._frozen = False
        self._frozen_reason = None
        self.logger.info('start_day balance=%.2f', float(self._start_balance))

    def _check_daily_loss(self, price_map: dict | None = None) -> bool:
        if self._start_balance is None:
            return True
        cur = self._get_balance(price_map or {})
        loss = (self._start_balance - cur) / self._start_balance
        if loss >= self.daily_loss_limit:
            self._frozen = True
            self._frozen_reason = f'daily loss exceeded: {loss:.3f} >= {self.daily_loss_limit}'
            ev = {'type': 'daily_loss_freeze', 'loss': loss, 'limit': self.daily_loss_limit, 'reason': self._frozen_reason}
            self.logger.warning('execution frozen: %s', self._frozen_reason)
            self._alert(ev)
            return False
        return True

    def pre_trade_check(self, symbol: str, side: str, qty: int, price: float, previous_close: Optional[float] = None) -> tuple[bool, str]:
        if self._frozen:
            return False, f'Execution frozen: {self._frozen_reason}'

        # check quantity
        if qty <= 0:
            return False, 'qty must be > 0'

        # position limit
        pos_map = self._get_positions()
        pos = int(pos_map.get(symbol, 0))
        if side.lower() == 'buy' and (pos + qty) > self.max_position_per_symbol:
            return False, f'position limit exceeded for {symbol}: {pos + qty} > {self.max_position_per_symbol}'

        # check ARA/ARB using previous_close when provided, else use price
        pc = float(previous_close) if previous_close is not None else float(price)
        limits = calculate_idx_limits(pc)
        ara = limits['ara']
        arb = limits['arb']

        if side.lower() == 'buy' and price > ara:
            return False, f'price {price} above ARA {ara}'
        if side.lower() == 'sell' and price < arb:
            return False, f'price {price} below ARB {arb}'

        # check total notional
        total_notional = sum(v * price for k, v in pos_map.items()) + qty * price
        if total_notional > self.max_total_notional:
            return False, f'total notional limit exceeded: {total_notional} > {self.max_total_notional}'

        # daily loss check
        ok = self._check_daily_loss({symbol: price})
        if not ok:
            return False, f'execution frozen by daily loss check: {self._frozen_reason}'

        return True, 'ok'

    def place_order(self, symbol: str, side: str, qty: int, price: float, previous_close: Optional[float] = None):
        ok, reason = self.pre_trade_check(symbol, side, qty, price, previous_close=previous_close)
        if not ok:
            ev = {'type': 'order_rejected', 'symbol': symbol, 'side': side, 'qty': qty, 'price': price, 'reason': reason}
            self.logger.info('order rejected: %s', ev)
            self._alert(ev)
            return {'status': 'rejected', 'reason': reason}

        trade = self._place(symbol, side, qty, price)

        # update daily-loss after trade
        self._check_daily_loss({symbol: price})

        # notify on fills
        try:
            if trade.get('status') == 'filled':
                ev = {'type': 'order_filled', 'trade': trade}
                self.logger.info('order filled: %s', trade)
                self._alert(ev)
        except Exception:
            self.logger.exception('error processing trade notification')

        return trade

    def get_balance(self, price_map: dict | None = None):
        return self._get_balance(price_map or {})
