"""Trade reconciliation helper to align local DB state with broker state.

Provides an async helper that checks pending local orders and reconciles
their status with the broker's active orders/trade history.
"""
from __future__ import annotations

import asyncio
from typing import Any


class TradeReconciler:
    def __init__(self, broker_client: Any, local_db: Any):
        self.broker = broker_client
        self.db = local_db

    async def reconcile_unsettled_orders(self):
        pending_local_orders = await self.db.get_orders_by_status('PENDING')

        live_broker_orders = await self.broker.get_active_orders()
        live_broker_order_ids = {o['id']: o for o in live_broker_orders}

        for local_order in pending_local_orders:
            if local_order['id'] not in live_broker_order_ids:
                trade_history = await self.broker.get_trade_history(symbol=local_order['symbol'])
                matched_trade = next((t for t in trade_history if t.get('order_id') == local_order['id']), None)
                if matched_trade:
                    await self.db.update_order_status(
                        local_order['id'],
                        status='FILLED',
                        filled_price=matched_trade.get('price'),
                        filled_qty=matched_trade.get('volume'),
                    )
                else:
                    await self.db.update_order_status(local_order['id'], status='REJECTED')
