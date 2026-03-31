"""Execution manager wrapping a broker adapter and enforcing pre-trade risk checks.

This manager accepts either the project's `PaperBroker` or any adapter
implementing the `BrokerAdapter` interface (see `src.brokers.base`). It
adds optional alert callbacks and logging while maintaining backward
compatibility with existing code.
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Optional, Callable, Any, Dict

from .idx_rules import calculate_idx_limits

# Optional Prometheus metrics (graceful fallback when prometheus_client is absent)
try:
    from prometheus_client import Counter, Gauge

    ORDERS_PLACED = Counter('autosaham_orders_placed_total', 'Number of orders placed')
    ORDERS_REJECTED = Counter('autosaham_orders_rejected_total', 'Number of orders rejected')
    ORDERS_FILLED = Counter('autosaham_orders_filled_total', 'Number of orders filled')
    PENDING_ORDERS = Gauge('autosaham_pending_orders', 'Number of pending limit orders')
    PENDING_CREATED = Counter('autosaham_pending_orders_created_total', 'Pending limit orders created')
    PENDING_REMOVED = Counter('autosaham_pending_orders_removed_total', 'Pending limit orders removed')
    DAILY_FREEZES = Counter('autosaham_daily_freezes_total', 'Number of daily loss freezes')
    PROM_AVAILABLE = True
except Exception:
    ORDERS_PLACED = None
    ORDERS_REJECTED = None
    ORDERS_FILLED = None
    PENDING_ORDERS = None
    PENDING_CREATED = None
    PENDING_REMOVED = None
    DAILY_FREEZES = None
    PROM_AVAILABLE = False

try:
    # optional import; available when broker adapters added
    from src.brokers.base import BrokerAdapter
except Exception:
    BrokerAdapter = None  # type: ignore

try:
    from src.alerts.webhook import send_alert_webhook
except Exception:
    send_alert_webhook = None


class ExecutionManager:
    def __init__(
        self,
        broker: Optional[Any] = None,
        max_position_per_symbol: int = 1000,
        max_total_notional: float = 1e9,
        daily_loss_limit: float = 0.05,
        alert_callback: Optional[Callable[[dict], None]] = None,
        alert_webhooks: Optional[list] = None,
        logger: Optional[logging.Logger] = None,
    ):
        # keep backward compat: broker may be a PaperBroker instance
        self.broker = broker
        self.max_position_per_symbol = int(max_position_per_symbol)
        self.max_total_notional = float(max_total_notional)
        self.daily_loss_limit = float(daily_loss_limit)
        self._start_balance = None
        self._frozen = False
        self._frozen_reason = None
        self.alert_callback = alert_callback
        # optional list of webhook URLs to POST alerts to (best-effort)
        self.alert_webhooks = list(alert_webhooks) if alert_webhooks else []
        self.logger = logger or logging.getLogger('autosaham.execution')

        # lazily create a default paper broker if none provided
        if self.broker is None:
            try:
                from .executor import PaperBroker

                self.broker = PaperBroker()
            except Exception:
                self.broker = None
        # pending limit orders bookkeeping
        self.pending_orders: dict = {}
        self._next_order_id = 1
        self.pending_orders: dict = {}
        # expected state tracked locally for reconciliation checks
        self._expected_positions: Dict[str, int] = {}
        self._expected_cash: Optional[float] = None
        # reconciliation background loop
        self._recon_thread: Optional[threading.Thread] = None
        self._recon_stop_event = threading.Event()

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
        # also attempt to send to configured webhook URLs (best-effort)
        try:
            if getattr(self, 'alert_webhooks', None) and send_alert_webhook:
                payload = {'ts': int(time.time()), 'event': ev}
                for url in list(self.alert_webhooks):
                    try:
                        send_alert_webhook(url, payload)
                    except Exception:
                        self.logger.exception('failed sending webhook alert to %s', url)
        except Exception:
            self.logger.exception('webhook alert flow failed')
        # best-effort: push to API event queue for WebSocket clients
        try:
            from src.api.event_queue import push_event  # type: ignore

            try:
                push_event(ev)
            except Exception:
                pass
        except Exception:
            pass

    # --- public methods ---
    def start_day(self, price_map: dict | None = None):
        # record starting balance for the day
        self._start_balance = self._get_balance(price_map or {})
        self._frozen = False
        self._frozen_reason = None
        self.logger.info('start_day balance=%.2f', float(self._start_balance))
        # initialize expected positions/cash from broker if available
        try:
            self._expected_positions = dict(self._get_positions())
            if hasattr(self.broker, 'get_cash'):
                self._expected_cash = float(self.broker.get_cash())
            else:
                # best-effort fallback: use cash attribute or balance
                self._expected_cash = float(getattr(self.broker, 'cash', self._get_balance({})))
        except Exception:
            self._expected_positions = {}
            self._expected_cash = None

    def _check_daily_loss(self, price_map: dict | None = None) -> bool:
        if self._start_balance is None:
            return True
        cur = self._get_balance(price_map or {})
        loss = (self._start_balance - cur) / self._start_balance
        if loss >= self.daily_loss_limit:
            self._frozen = True
            self._frozen_reason = (
                f'daily loss exceeded: {loss:.3f} >= {self.daily_loss_limit}'
            )
            ev = {
                'type': 'daily_loss_freeze',
                'loss': loss,
                'limit': self.daily_loss_limit,
                'reason': self._frozen_reason,
            }
            self.logger.warning('execution frozen: %s', self._frozen_reason)
            self._alert(ev)
            try:
                if DAILY_FREEZES:
                    DAILY_FREEZES.inc()
            except Exception:
                pass
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
            return False, (
                f'position limit exceeded for {symbol}: '
                f'{pos + qty} > {self.max_position_per_symbol}'
            )

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
            return False, (
                f'total notional limit exceeded: {total_notional} > '
                f'{self.max_total_notional}'
            )

        # daily loss check
        ok = self._check_daily_loss({symbol: price})
        if not ok:
            return False, f'execution frozen by daily loss check: {self._frozen_reason}'

        return True, 'ok'

    def place_order(self, symbol: str, side: str, qty: int, price: float, previous_close: Optional[float] = None):
        ok, reason = self.pre_trade_check(symbol, side, qty, price, previous_close=previous_close)
        if not ok:
            ev = {
                'type': 'order_rejected',
                'symbol': symbol,
                'side': side,
                'qty': qty,
                'price': price,
                'reason': reason,
            }
            self.logger.info('order rejected: %s', ev)
            self._alert(ev)
            return {'status': 'rejected', 'reason': reason}

        trade = self._place(symbol, side, qty, price)

        # update expected state and daily-loss after trade
        try:
            if trade.get('status') == 'filled':
                self._apply_trade_to_expected(trade)
        except Exception:
            self.logger.exception('failed to update expected state after trade')

        self._check_daily_loss({symbol: price})

        # notify on fills
        try:
            if trade.get('status') == 'filled':
                ev = {'type': 'order_filled', 'trade': trade}
                self.logger.info('order filled: %s', trade)
                self._alert(ev)
                try:
                    if ORDERS_FILLED:
                        ORDERS_FILLED.inc()
                except Exception:
                    pass
        except Exception:
            self.logger.exception('error processing trade notification')

        return trade

    def get_balance(self, price_map: dict | None = None):
        return self._get_balance(price_map or {})

    def calculate_dynamic_position_size(
        self,
        win_rate: float,
        reward_to_risk_ratio: float,
        account_balance: float,
        stock_volatility_atr: float,
        target_portfolio_volatility: float = 0.02,
    ) -> int:
        """
        Calculate an allocation (currency units) using a Half-Kelly fraction
        combined with volatility targeting.

        Returns an integer capital allocation (Rupiah). Callers may convert this
        to a number of shares/lots by dividing by current price.
        """
        try:
            import math

            # Full Kelly: f* = W - [(1 - W) / R]
            kelly_fraction = float(win_rate) - ((1.0 - float(win_rate)) / max(float(reward_to_risk_ratio), 1e-6))
            # Use half-Kelly for safety
            safe_kelly = max(0.0, kelly_fraction / 2.0)

            # Volatility targeting scalar (reduce size for high ATR)
            volatility_scalar = float(target_portfolio_volatility) / max(float(stock_volatility_atr), 1e-4)

            allocated_capital = float(account_balance) * safe_kelly * volatility_scalar

            # Hard cap: do not allocate more than 20% of account to a single emitter
            allocated_capital = min(allocated_capital, float(account_balance) * 0.20)

            return int(max(0, allocated_capital))
        except Exception:
            return 0

    def detect_false_breakout(self, current_volume: float, ma20_volume: float, threshold: float = 0.6) -> bool:
        """
        Simple VPA-based false-breakout detector.

        Returns True when the current volume is substantially below the MA-20
        (suggesting low participation) and a breakout should be treated as
        suspicious. Threshold is the fraction of MA-20 below which we flag.
        """
        try:
            if ma20_volume is None or ma20_volume <= 0:
                return False
            return float(current_volume) < float(ma20_volume) * float(threshold)
        except Exception:
            return False

    # --- limit / pending order helpers ---
    def _generate_order_id(self) -> str:
        oid = f'lim-{self._next_order_id}'
        self._next_order_id += 1
        return oid

    def place_limit_order(self, symbol: str, side: str, qty: int, limit_price: float, previous_close: Optional[float] = None) -> dict:
        """Register a pending limit order. Performs light validation (qty, pos limit,
        and ARA/ARB bounds) and returns a pending order id on success.
        """
        side_l = side.lower()
        qty = int(qty)
        if qty <= 0:
            return {'status': 'rejected', 'reason': 'qty must be > 0'}

        pos_map = self._get_positions()
        pos = int(pos_map.get(symbol, 0))
        if side_l == 'buy' and (pos + qty) > self.max_position_per_symbol:
            return {'status': 'rejected', 'reason': f'position limit exceeded for {symbol}'}

        # validate against ARA/ARB using previous_close when provided
        pc = float(previous_close) if previous_close is not None else float(limit_price)
        limits = calculate_idx_limits(pc)
        ara = limits['ara']
        arb = limits['arb']
        if side_l == 'buy' and float(limit_price) > ara:
            return {'status': 'rejected', 'reason': f'limit price {limit_price} above ARA {ara}'}
        if side_l == 'sell' and float(limit_price) < arb:
            return {'status': 'rejected', 'reason': f'limit price {limit_price} below ARB {arb}'}

        oid = self._generate_order_id()
        order = {
            'order_id': oid,
            'symbol': symbol,
            'side': side_l,
            'qty': qty,
            'limit_price': float(limit_price),
            'previous_close': previous_close,
        }
        self.pending_orders[oid] = order
        ev = {'type': 'order_queued', 'order': order}
        self.logger.info('limit order queued: %s', order)
        self._alert(ev)
        try:
            if PENDING_CREATED:
                PENDING_CREATED.inc()
            if PENDING_ORDERS:
                PENDING_ORDERS.set(len(self.pending_orders))
        except Exception:
            pass
        return {'status': 'pending', 'order_id': oid}

    def cancel_limit_order(self, order_id: str) -> bool:
        if order_id in self.pending_orders:
            order = self.pending_orders.pop(order_id)
            ev = {'type': 'order_cancelled', 'order': order}
            self.logger.info('limit order cancelled: %s', order)
            self._alert(ev)
            try:
                if PENDING_REMOVED:
                    PENDING_REMOVED.inc()
                if PENDING_ORDERS:
                    PENDING_ORDERS.set(len(self.pending_orders))
            except Exception:
                pass
            return True
        return False

    def cancel_all_pending_for_symbol(self, symbol: str) -> int:
        removed = []
        for oid, o in list(self.pending_orders.items()):
            if o.get('symbol') == symbol:
                removed.append(oid)
                self.pending_orders.pop(oid, None)
                self._alert({'type': 'order_cancelled', 'order': o})
        try:
            if PENDING_REMOVED:
                # increment by number removed
                for _ in removed:
                    PENDING_REMOVED.inc()
            if PENDING_ORDERS:
                PENDING_ORDERS.set(len(self.pending_orders))
        except Exception:
            pass
        return len(removed)

    def get_pending_orders(self) -> list:
        return list(self.pending_orders.values())

    def process_market_tick(self, price_map: dict) -> dict:
        """Check pending limit orders against current market prices and execute if triggered.

        Returns a dict with executed and rejected lists.
        """
        executed = []
        rejected = []
        to_remove = []
        for oid, order in list(self.pending_orders.items()):
            sym = order.get('symbol')
            side = order.get('side')
            qty = int(order.get('qty', 0))
            limit_price = float(order.get('limit_price', 0.0))
            prev_close = order.get('previous_close')
            cur_price = price_map.get(sym)
            if cur_price is None:
                continue
            trigger = False
            if side == 'sell' and cur_price >= limit_price:
                trigger = True
            if side == 'buy' and cur_price <= limit_price:
                trigger = True
            if not trigger:
                continue

            # light pre-check at execution time
            ok, reason = True, 'ok'
            try:
                ok, reason = self.pre_trade_check(sym, side, qty, cur_price, previous_close=prev_close)
            except Exception:
                ok, reason = False, 'pre_trade_check_error'

            if not ok:
                ev = {
                    'type': 'order_rejected',
                    'order': order,
                    'reason': reason,
                }
                self.logger.info('pending limit rejected: %s', ev)
                self._alert(ev)
                rejected.append({'order': order, 'reason': reason})
                to_remove.append(oid)
                continue

            trade = self._place(sym, side, qty, cur_price)
            if trade.get('status') == 'filled':
                ev = {
                    'type': 'order_filled',
                    'trade': trade,
                    'origin_order': order,
                }
                self.logger.info('pending limit filled: %s', ev)
                self._alert(ev)
                executed.append({'order': order, 'trade': trade})
                to_remove.append(oid)
                try:
                    if ORDERS_FILLED:
                        ORDERS_FILLED.inc()
                except Exception:
                    pass
                # update expected state for filled pending order
                try:
                    self._apply_trade_to_expected(trade)
                except Exception:
                    self.logger.exception('failed to update expected state after pending fill')
            else:
                ev = {
                    'type': 'order_rejected',
                    'order': order,
                    'trade': trade,
                }
                self.logger.info('pending limit broker rejected: %s', ev)
                self._alert(ev)
                rejected.append({'order': order, 'trade': trade})
                to_remove.append(oid)

        # remove processed orders
        for oid in to_remove:
            self.pending_orders.pop(oid, None)

        # update daily loss baseline
        try:
            self._check_daily_loss(price_map)
        except Exception:
            pass

        # update pending orders gauge
        try:
            if PENDING_ORDERS:
                PENDING_ORDERS.set(len(self.pending_orders))
        except Exception:
            pass

        # update daily loss baseline
        try:
            self._check_daily_loss(price_map)
        except Exception:
            pass

        return {'executed': executed, 'rejected': rejected}

    # --- reconciliation helpers ---
    def _apply_trade_to_expected(self, trade: dict) -> None:
        try:
            sym = trade.get('symbol')
            side = str(trade.get('side', '')).lower()
            qty = int(trade.get('qty', 0))
            price = float(trade.get('price', 0.0))
            fee = float(trade.get('fee', 0.0)) if trade.get('fee') is not None else 0.0
            if not sym:
                return
            if side == 'buy':
                self._expected_positions[sym] = self._expected_positions.get(sym, 0) + qty
                if self._expected_cash is not None:
                    self._expected_cash -= (qty * price + fee)
            elif side == 'sell':
                self._expected_positions[sym] = self._expected_positions.get(sym, 0) - qty
                if self._expected_cash is not None:
                    net = float(trade.get('net', price * qty - fee))
                    self._expected_cash += net
        except Exception:
            self.logger.exception('error applying trade to expected state')

    def reconcile_once(self, alert_on_drift: bool = True) -> dict:
        """Perform a single reconciliation check between expected state and broker snapshot.

        Returns the reconciliation report from the adapter (or a generated report).
        """
        if self.broker is None:
            return {'ok': True, 'reason': 'no_broker'}

        expected_positions = dict(self._expected_positions or {})
        expected_cash = self._expected_cash
        # if we have no expected snapshot, default to current positions
        if expected_positions == {}:
            expected_positions = dict(self._get_positions())

        try:
            if hasattr(self.broker, 'reconcile_with_expected'):
                report = self.broker.reconcile_with_expected(expected_positions, expected_cash)
            elif hasattr(self.broker, 'reconcile'):
                snap = self.broker.reconcile() or {}
                diffs = {}
                actual_pos = snap.get('positions', {})
                for sym, exp_qty in (expected_positions or {}).items():
                    act_qty = actual_pos.get(sym, 0)
                    if act_qty != exp_qty:
                        diffs.setdefault('positions', {})[sym] = {
                            'expected': int(exp_qty),
                            'actual': int(act_qty),
                        }
                if expected_cash is not None:
                    act_cash = float(snap.get('cash', 0.0))
                    if abs(act_cash - float(expected_cash)) > 1e-6:
                        diffs['cash'] = {'expected': float(expected_cash), 'actual': act_cash}
                report = {'ok': len(diffs) == 0, 'diffs': diffs, 'snapshot': snap}
            else:
                report = {'ok': True, 'reason': 'no_reconcile_api'}
        except Exception as e:
            self.logger.exception('reconciliation failed')
            return {'ok': False, 'error': str(e)}

        if not report.get('ok', False):
            ev = {'type': 'reconcile_drift', 'report': report}
            self.logger.warning('reconciliation drift detected: %s', report)
            if alert_on_drift:
                self._alert(ev)

        return report

    def start_reconciliation_loop(self, interval_seconds: int = 60, alert_on_drift: bool = True) -> bool:
        """Start a background thread that periodically calls `reconcile_once`.

        Returns True if a new loop was started, False if one is already running.
        """
        if self._recon_thread and self._recon_thread.is_alive():
            return False

        self._recon_stop_event.clear()

        def _run():
            while not self._recon_stop_event.wait(interval_seconds):
                try:
                    self.reconcile_once(alert_on_drift=alert_on_drift)
                except Exception:
                    self.logger.exception('reconciliation loop error')

        self._recon_thread = threading.Thread(target=_run, name='ExecutionManagerReconcile', daemon=True)
        self._recon_thread.start()
        return True

    def stop_reconciliation_loop(self, timeout: float = 5.0) -> None:
        """Stop a running reconciliation loop and wait for the thread to exit."""
        try:
            if not self._recon_thread:
                return
            self._recon_stop_event.set()
            self._recon_thread.join(timeout)
            self._recon_thread = None
        except Exception:
            self.logger.exception('error stopping reconciliation loop')
