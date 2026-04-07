"""Trade reconciliation helper to align local DB state with broker state.

Provides an async helper that checks pending local orders and reconciles
their status with the broker's active orders/trade history.
"""
from __future__ import annotations

from typing import Any


def _to_non_negative_int(value: Any) -> int:
    try:
        return max(0, int(value))
    except Exception:
        return 0


def _to_non_negative_float(value: Any) -> float:
    try:
        return max(0.0, float(value))
    except Exception:
        return 0.0


class TradeReconciler:
    def __init__(self, broker_client: Any, local_db: Any):
        self.broker = broker_client
        self.db = local_db

    async def reconcile_unsettled_orders(self):
        pending_local_orders = await self.db.get_orders_by_status("PENDING")

        live_broker_orders = await self.broker.get_active_orders()
        live_broker_order_ids = {o["id"]: o for o in live_broker_orders}

        for local_order in pending_local_orders:
            if local_order["id"] not in live_broker_order_ids:
                trade_history = await self.broker.get_trade_history(
                    symbol=local_order["symbol"]
                )
                matched_trades = [
                    t
                    for t in (trade_history or [])
                    if t.get("order_id") == local_order["id"]
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
                    continue

                is_partial_fill = requested_qty > 0 and total_filled_qty < requested_qty
                await self.db.update_order_status(
                    local_order["id"],
                    status="PARTIALLY_FILLED" if is_partial_fill else "FILLED",
                    filled_price=avg_fill_price,
                    filled_qty=total_filled_qty,
                )
