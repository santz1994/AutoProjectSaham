"""Execution algorithms: TWAP / VWAP order slicing utilities.

These algorithms are intentionally simple building blocks — integrate with a
broker adapter that implements `get_quote()` and `place_order()` async APIs.
"""
from __future__ import annotations

import asyncio
import random
from typing import Any


async def execute_twap_order(
    api_client: Any,
    symbol: str,
    total_volume_lots: int,
    duration_minutes: int,
    max_price_limit: float,
):
    """
    Split a large order into smaller slices executed over `duration_minutes`.

    The `api_client` must expose async `get_quote(symbol)` returning a dict with
    a `best_ask` key and `place_order(symbol, action, volume, price)` that
    executes the slice.
    """
    # Minimal slicing: at least 5 slices
    slices = max(5, int(duration_minutes) // 5)
    base_lots = max(1, int(total_volume_lots) // slices)

    lots_remaining = int(total_volume_lots)

    for i in range(slices):
        if lots_remaining <= 0:
            break

        noise = random.uniform(-0.2, 0.2)
        current_slice = max(1, int(base_lots * (1 + noise)))

        if i == slices - 1 or current_slice > lots_remaining:
            current_slice = lots_remaining

        try:
            current_market = await api_client.get_quote(symbol)
            best_ask = float(current_market.get("best_ask", 0.0))
        except Exception:
            best_ask = None

        if best_ask is not None and (
            max_price_limit is None or best_ask <= float(max_price_limit)
        ):
            try:
                await api_client.place_order(
                    symbol, action="BUY", volume=current_slice, price=best_ask
                )
                lots_remaining -= current_slice
            except Exception:
                # best-effort: skip a slice on error
                await asyncio.sleep(0.5)

        # randomized sleep to avoid deterministic patterns
        sleep_base = (duration_minutes * 60) / slices
        await asyncio.sleep(sleep_base * random.uniform(0.8, 1.2))

    return {"status": "done", "remaining": max(0, lots_remaining)}
