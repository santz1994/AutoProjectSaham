"""Local exchange simulator for execution chaos testing.

The simulator is deterministic when seeded and models:
- latency spikes
- partial fills
- cancel race conditions
"""

from __future__ import annotations

import random
import time
from dataclasses import dataclass
from typing import List, Optional


@dataclass
class SimulationConfig:
    min_latency_ms: int = 20
    max_latency_ms: int = 250
    partial_fill_probability: float = 0.25
    cancel_race_probability: float = 0.10
    reject_probability: float = 0.02


@dataclass
class OrderIntent:
    symbol: str
    side: str
    quantity: int
    order_type: str = "limit"
    price: Optional[float] = None


@dataclass
class SimulationEvent:
    name: str
    timestamp_ms: int
    quantity: int = 0
    note: Optional[str] = None


@dataclass
class SimulationResult:
    order_id: str
    status: str
    filled_quantity: int
    remaining_quantity: int
    avg_fill_price: float
    latency_ms: int
    events: List[SimulationEvent]


class LocalExchangeSimulator:
    """Deterministic local simulator for exchange execution behavior."""

    def __init__(self, config: Optional[SimulationConfig] = None, seed: Optional[int] = None):
        self.config = config or SimulationConfig()
        self._rng = random.Random(seed)
        self._order_seq = 1

    def _next_order_id(self) -> str:
        order_id = f"sim-{self._order_seq}"
        self._order_seq += 1
        return order_id

    def _sample_latency_ms(self) -> int:
        floor = max(1, int(self.config.min_latency_ms))
        ceil = max(floor, int(self.config.max_latency_ms))
        return int(self._rng.randint(floor, ceil))

    def simulate_order(self, order: OrderIntent) -> SimulationResult:
        if int(order.quantity) <= 0:
            raise ValueError("quantity must be > 0")

        order_id = self._next_order_id()
        now_ms = int(time.time() * 1000)
        latency_ms = self._sample_latency_ms()
        accepted_ts = now_ms + latency_ms

        events: List[SimulationEvent] = [
            SimulationEvent(name="accepted", timestamp_ms=accepted_ts),
        ]

        if self._rng.random() < float(self.config.reject_probability):
            events.append(
                SimulationEvent(
                    name="rejected",
                    timestamp_ms=accepted_ts + 1,
                    note="exchange_reject",
                )
            )
            return SimulationResult(
                order_id=order_id,
                status="rejected",
                filled_quantity=0,
                remaining_quantity=int(order.quantity),
                avg_fill_price=0.0,
                latency_ms=latency_ms,
                events=events,
            )

        price = float(order.price or 0.0)
        quantity = int(order.quantity)

        if quantity > 1 and self._rng.random() < float(self.config.partial_fill_probability):
            partial_qty = int(self._rng.randint(1, quantity - 1))
            remaining = quantity - partial_qty

            events.append(
                SimulationEvent(
                    name="partial_fill",
                    timestamp_ms=accepted_ts + 2,
                    quantity=partial_qty,
                )
            )

            if self._rng.random() < float(self.config.cancel_race_probability):
                events.append(
                    SimulationEvent(
                        name="cancel_race",
                        timestamp_ms=accepted_ts + 3,
                        quantity=remaining,
                    )
                )

                cancel_wins = self._rng.random() < 0.5
                if cancel_wins:
                    events.append(
                        SimulationEvent(
                            name="cancelled",
                            timestamp_ms=accepted_ts + 4,
                            quantity=remaining,
                            note="cancel_won_race",
                        )
                    )
                    return SimulationResult(
                        order_id=order_id,
                        status="partially_filled",
                        filled_quantity=partial_qty,
                        remaining_quantity=remaining,
                        avg_fill_price=price,
                        latency_ms=latency_ms,
                        events=events,
                    )

            events.append(
                SimulationEvent(
                    name="filled",
                    timestamp_ms=accepted_ts + 4,
                    quantity=remaining,
                    note="post_partial_fill",
                )
            )
            return SimulationResult(
                order_id=order_id,
                status="filled",
                filled_quantity=quantity,
                remaining_quantity=0,
                avg_fill_price=price,
                latency_ms=latency_ms,
                events=events,
            )

        events.append(
            SimulationEvent(
                name="filled",
                timestamp_ms=accepted_ts + 2,
                quantity=quantity,
            )
        )
        return SimulationResult(
            order_id=order_id,
            status="filled",
            filled_quantity=quantity,
            remaining_quantity=0,
            avg_fill_price=price,
            latency_ms=latency_ms,
            events=events,
        )

    def simulate_batch(self, orders: List[OrderIntent]) -> List[SimulationResult]:
        return [self.simulate_order(order) for order in orders]
