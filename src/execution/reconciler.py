"""Trade reconciliation helper to align local DB state with broker state.

Provides an async helper that checks pending local orders and reconciles
their status with the broker's active orders/trade history.
"""
from __future__ import annotations

import inspect
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


def _to_non_negative_int(value: Any) -> int:
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return 0


def _to_non_negative_float(value: Any) -> float:
    try:
        return max(0.0, float(value))
    except (TypeError, ValueError):
        return 0.0


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _is_awaitable(value: Any) -> bool:
    try:
        return inspect.isawaitable(value)
    except TypeError:
        return False


def _normalize_side(order: Dict[str, Any]) -> str:
    raw = order.get("side") or order.get("action") or order.get("type") or "buy"
    return str(raw).strip().lower()


def _resolve_reference_price(order: Dict[str, Any], fallback: Optional[float]) -> float:
    candidates = [
        order.get("price"),
        order.get("limit_price"),
        order.get("entry_price"),
        order.get("avg_fill_price"),
        fallback,
    ]
    for item in candidates:
        value = _to_non_negative_float(item)
        if value > 0:
            return value
    return 0.0


class TradeReconciler:
    """Reconcile pending orders and emit margin ledger journal entries.

    The reconciler maintains a lightweight double-entry style journal for each
    processed order to keep `locked margin` and `free margin` movements
    auditable. If a sink callable (sync/async) is provided, each entry is
    forwarded for persistence.
    """

    def __init__(
        self,
        broker_client: Any,
        local_db: Any,
        ledger_sink: Optional[Any] = None,
    ):
        self.broker = broker_client
        self.db = local_db
        self.ledger_sink = ledger_sink
        self._ledger_journal: List[Dict[str, Any]] = []

    def get_ledger_journal(self) -> List[Dict[str, Any]]:
        return [dict(item) for item in self._ledger_journal]

    async def _emit_ledger_entry(self, entry: Dict[str, Any]) -> None:
        self._ledger_journal.append(dict(entry))

        sink = self.ledger_sink
        if sink is None:
            sink = getattr(self.db, "record_ledger_entry", None)

        if callable(sink):
            result = sink(entry)
            if _is_awaitable(result):
                await result

    def _build_ledger_entry(
        self,
        local_order: Dict[str, Any],
        *,
        status: str,
        requested_qty: int,
        filled_qty: int,
        avg_fill_price: Optional[float],
    ) -> Dict[str, Any]:
        side = _normalize_side(local_order)
        is_sell = side == "sell"
        price_reference = _resolve_reference_price(local_order, avg_fill_price)

        requested_notional = (
            float(requested_qty) * price_reference if requested_qty > 0 else 0.0
        )
        effective_fill_price = _to_non_negative_float(avg_fill_price) or price_reference
        filled_notional = (
            float(filled_qty) * effective_fill_price if filled_qty > 0 else 0.0
        )
        unfilled_notional = max(0.0, requested_notional - filled_notional)

        debit: Dict[str, float]
        credit: Dict[str, float]

        if status == "REJECTED" and not is_sell:
            debit = {"locked_margin": requested_notional}
            credit = {"free_margin": requested_notional}
        elif is_sell:
            debit = {"asset_inventory": filled_notional}
            credit = {"free_margin": filled_notional}
        else:
            debit = {"locked_margin": requested_notional}
            credit = {
                "asset_inventory": filled_notional,
                "free_margin": unfilled_notional,
            }

        return {
            "order_id": local_order.get("id"),
            "symbol": local_order.get("symbol"),
            "side": side,
            "status": status,
            "requested_qty": requested_qty,
            "filled_qty": filled_qty,
            "requested_notional": requested_notional,
            "filled_notional": filled_notional,
            "debit": debit,
            "credit": credit,
            "timestamp": _utc_now_iso(),
        }

    async def reconcile_unsettled_orders(self):
        pending_local_orders = await self.db.get_orders_by_status("PENDING")

        live_broker_orders = await self.broker.get_active_orders()
        live_broker_order_ids = {
            str(order.get("id")): order
            for order in (live_broker_orders or [])
            if isinstance(order, dict) and order.get("id") is not None
        }

        for local_order in pending_local_orders:
            local_order_id = str(local_order.get("id"))
            if local_order_id not in live_broker_order_ids:
                trade_history = await self.broker.get_trade_history(
                    symbol=local_order["symbol"]
                )
                matched_trades = [
                    t
                    for t in (trade_history or [])
                    if str(t.get("order_id")) == local_order_id
                ]

                requested_qty = _to_non_negative_int(
                    local_order.get("quantity")
                    or local_order.get("qty")
                    or local_order.get("volume")
                )

                total_filled_qty = int(
                    sum(
                        _to_non_negative_int(t.get("volume") or t.get("qty"))
                        for t in matched_trades
                    )
                )
                total_notional = float(
                    sum(
                        _to_non_negative_float(t.get("price"))
                        * float(_to_non_negative_int(t.get("volume") or t.get("qty")))
                        for t in matched_trades
                    )
                )
                avg_fill_price = (
                    float(total_notional / total_filled_qty)
                    if total_filled_qty > 0
                    else None
                )

                if total_filled_qty <= 0:
                    await self.db.update_order_status(
                        local_order["id"], status="REJECTED"
                    )
                    await self._emit_ledger_entry(
                        self._build_ledger_entry(
                            local_order,
                            status="REJECTED",
                            requested_qty=requested_qty,
                            filled_qty=0,
                            avg_fill_price=avg_fill_price,
                        )
                    )
                    continue

                is_partial_fill = requested_qty > 0 and total_filled_qty < requested_qty
                resolved_status = "PARTIALLY_FILLED" if is_partial_fill else "FILLED"
                requested_notional = float(requested_qty) * _resolve_reference_price(
                    local_order,
                    avg_fill_price,
                )
                filled_notional = float(total_filled_qty) * _to_non_negative_float(
                    avg_fill_price
                )
                await self.db.update_order_status(
                    local_order["id"],
                    status=resolved_status,
                    filled_price=avg_fill_price,
                    filled_qty=total_filled_qty,
                    requested_notional=requested_notional,
                    filled_notional=filled_notional,
                    remaining_notional=max(0.0, requested_notional - filled_notional),
                )
                await self._emit_ledger_entry(
                    self._build_ledger_entry(
                        local_order,
                        status=resolved_status,
                        requested_qty=requested_qty,
                        filled_qty=total_filled_qty,
                        avg_fill_price=avg_fill_price,
                    )
                )
