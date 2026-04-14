from __future__ import annotations

import argparse
import json

from src.execution.exchange_simulator import (
    LocalExchangeSimulator,
    OrderIntent,
    SimulationConfig,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run local exchange chaos simulation for execution paths.",
    )
    parser.add_argument("--orders", type=int, default=10)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--min-latency-ms", type=int, default=20)
    parser.add_argument("--max-latency-ms", type=int, default=250)
    parser.add_argument("--partial-prob", type=float, default=0.25)
    parser.add_argument("--cancel-race-prob", type=float, default=0.10)
    parser.add_argument("--reject-prob", type=float, default=0.02)
    args = parser.parse_args()

    cfg = SimulationConfig(
        min_latency_ms=args.min_latency_ms,
        max_latency_ms=args.max_latency_ms,
        partial_fill_probability=args.partial_prob,
        cancel_race_probability=args.cancel_race_prob,
        reject_probability=args.reject_prob,
    )
    sim = LocalExchangeSimulator(config=cfg, seed=args.seed)

    intents = []
    for i in range(max(1, int(args.orders))):
        side = "buy" if i % 2 == 0 else "sell"
        intents.append(
            OrderIntent(
                symbol="EURUSD=X",
                side=side,
                quantity=1,
                order_type="limit",
                price=1.08 + (float(i) * 0.0001),
            )
        )

    results = sim.simulate_batch(intents)

    summary = {
        "orders": len(results),
        "filled": sum(1 for item in results if item.status == "filled"),
        "partially_filled": sum(
            1 for item in results if item.status == "partially_filled"
        ),
        "rejected": sum(1 for item in results if item.status == "rejected"),
        "avgLatencyMs": (
            sum(item.latency_ms for item in results) / len(results)
            if results
            else 0.0
        ),
    }

    print(json.dumps({"summary": summary}, indent=2))


if __name__ == "__main__":
    main()
