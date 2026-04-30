"""Event-driven backtester for IDX that simulates price-time priority matching.

This module provides a conservative simulation of queue position and fills
based on traded volume at a given price level. It is intentionally
conservative (worst-case execution) to avoid liquidity illusions.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Optional


@dataclass
class OrderEvent:
    symbol: str
    order_type: str  # 'BUY' or 'SELL'
    price: int
    volume: int
    timestamp: float


class IDXEventDrivenBacktester:
    def __init__(self):
        self.order_queue = deque()
        self.current_market_data = {"traded_volume": 0}
        self.trades = []

    def update_market_data(self, traded_volume: int):
        self.current_market_data["traded_volume"] = int(traded_volume)

    def simulate_idx_matching_engine(
        self, order: OrderEvent, current_volume_at_price: int
    ) -> Optional[int]:
        """
        Simulate Price-Time Priority BEI.

        Conservative assumption: our order sits at the tail of the queue. We
        only get filled if traded_volume at that price consumes the queue ahead
        of us. Returns executed volume or None if no fill.
        """
        queue_position_ahead = int(current_volume_at_price)
        executed_volume = 0

        traded = int(self.current_market_data.get("traded_volume", 0))
        # while there is traded volume above the queue ahead and we still have volume
        while traded > queue_position_ahead and order.volume > 0:
            fill_amount = min(order.volume, traded - queue_position_ahead)
            executed_volume += fill_amount
            order.volume -= fill_amount
            queue_position_ahead += fill_amount

        return executed_volume if executed_volume > 0 else None

    def add_order(self, order: OrderEvent) -> None:
        """Add an order event to the internal queue (FIFO, worst-case placement)."""
        self.order_queue.append(order)

    def process_tick(self, traded_volume_at_price: int, price: float) -> list:
        """
        Process a market tick where `traded_volume_at_price` volume traded at `price`.

        Attempts to fill queued orders at this price following price-time priority.
        Returns a list of fill dicts: {'order': OrderEvent, 'filled': int}.
        """
        self.update_market_data(traded_volume_at_price)
        fills = []
        # iterate over a snapshot of the queue to avoid modification during iteration
        for order in list(self.order_queue):
            if order.price != int(price):
                # different price level; skip
                continue

            executed = self.simulate_idx_matching_engine(
                order, current_volume_at_price=0
            )
            if executed is not None and executed > 0:
                fills.append({"order": order, "filled": int(executed)})
                # record trade
                self.trades.append(
                    {
                        "symbol": order.symbol,
                        "side": order.order_type,
                        "price": order.price,
                        "volume": executed,
                        "timestamp": order.timestamp,
                    }
                )
                # remove order from queue if fully filled
                if order.volume <= 0:
                    try:
                        self.order_queue.remove(order)
                    except Exception:
                        pass

        return fills

    # Very small backtester for strategy signals.
    #
    # Executes signals at next-day prices (EoD semantics) to avoid lookahead bias
    # and supports deterministic slippage and fees for realistic simulation.


def simple_backtest(
    prices,
    signals,
    starting_cash=10000.0,
    lot_size=100,
    slippage_pct=0.0,
    buy_fee_pct=0.0015,
    sell_fee_pct=0.0025,
    allow_partial=False,
):
    """Run a simple backtest.

    - `prices`: list-like of prices indexed by day.
    - `signals`: list-like of same length as `prices`; a signal at index i is
      executed at the next day's price (prices[i+1]). Signals on the last day
      are ignored since there's no next-day price.
    - `slippage_pct`: deterministic slippage applied to gross value of trade.
    - `buy_fee_pct` / `sell_fee_pct`: broker fee percentages applied to gross.
    - `allow_partial`: if True, attempt to buy partial lots when cash insufficient.
    """
    cash = float(starting_cash)
    pos = 0
    trades = []

    n = len(prices)
    if n == 0:
        return {"final_balance": cash, "trades": trades}

    # iterate signals up to the penultimate day (signals on last day cannot execute)
    for i in range(0, n - 1):
        sig = signals[i]
        exec_idx = i + 1
        exec_price = float(prices[exec_idx])

        if sig == 1:
            qty = lot_size
            gross = exec_price * qty
            slippage_cost = gross * float(slippage_pct)
            fee = gross * float(buy_fee_pct)
            total_cost = gross + slippage_cost + fee
            if total_cost <= cash:
                cash -= total_cost
                pos += qty
                trades.append(
                    (
                        "buy",
                        exec_idx,
                        exec_price,
                        qty,
                        {"slippage": float(slippage_cost), "fee": float(fee)},
                    )
                )
            else:
                # attempt partial fill in whole lots if enabled
                if allow_partial and exec_price > 0:
                    per_share_cost = exec_price * (
                        1.0 + float(slippage_pct) + float(buy_fee_pct)
                    )
                    max_shares = int(cash // per_share_cost)
                    lots = max_shares // int(lot_size)
                    if lots > 0:
                        qty2 = lots * int(lot_size)
                        gross2 = exec_price * qty2
                        slippage2 = gross2 * float(slippage_pct)
                        fee2 = gross2 * float(buy_fee_pct)
                        total_cost2 = gross2 + slippage2 + fee2
                        cash -= total_cost2
                        pos += qty2
                        trades.append(
                            (
                                "buy_partial",
                                exec_idx,
                                exec_price,
                                qty2,
                                {"slippage": float(slippage2), "fee": float(fee2)},
                            )
                        )

        elif sig == -1 and pos > 0:
            qty = pos
            gross = exec_price * qty
            slippage_cost = gross * float(slippage_pct)
            fee = gross * float(sell_fee_pct)
            net_proceeds = gross - slippage_cost - fee
            cash += net_proceeds
            trades.append(
                (
                    "sell",
                    exec_idx,
                    exec_price,
                    qty,
                    {"slippage": float(slippage_cost), "fee": float(fee)},
                )
            )
            pos = 0

    final_bal = cash + pos * (prices[-1] if prices else 0)
    return {"final_balance": final_bal, "trades": trades}
