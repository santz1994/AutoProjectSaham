"""Run a constrained backtest to approximate live execution guardrails.

Example:
  python scripts/backtest_live_constraints.py --symbol BBCA.JK --max-drawdown-pct 0.05
"""

from __future__ import annotations

import argparse
import json
import os
import sys

import pandas as pd

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from src.backtest.vector_backtester import backtest_signals


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset-csv", default="data/dataset/dataset.csv")
    parser.add_argument("--symbol", default=None)
    parser.add_argument("--price-col", default=None)
    parser.add_argument("--signal-col", default="label")
    parser.add_argument("--initial-cash", type=float, default=100000.0)
    parser.add_argument("--commission-pct", type=float, default=0.0005)
    parser.add_argument("--slippage-pct", type=float, default=0.0005)
    parser.add_argument("--position-size", type=int, default=10)
    parser.add_argument("--max-exposure-pct", type=float, default=0.5)
    parser.add_argument("--max-position-units", type=int, default=None)
    parser.add_argument("--max-drawdown-pct", type=float, default=0.08)
    parser.add_argument("--trade-cooldown-bars", type=int, default=0)
    parser.add_argument("--max-total-trades", type=int, default=None)
    parser.add_argument("--report-out", default="models/transformers/live_constraints_backtest.json")
    args = parser.parse_args()

    if not os.path.exists(args.dataset_csv):
        raise RuntimeError(f"Dataset not found: {args.dataset_csv}")

    df = pd.read_csv(args.dataset_csv)
    if args.signal_col not in df.columns:
        raise RuntimeError(f"Signal column not found: {args.signal_col}")

    work = df.copy()
    if "symbol" in work.columns:
        if args.symbol:
            work = work[work["symbol"] == args.symbol]
        elif not work.empty:
            work = work[work["symbol"] == work["symbol"].iloc[0]]

    if "t_index" in work.columns:
        work = work.sort_values("t_index")

    if work.empty:
        raise RuntimeError("No rows available after symbol filtering")

    candidate_price_cols = [args.price_col, "last_price", "close", "entry_price"]
    price_col = next((c for c in candidate_price_cols if c and c in work.columns), None)
    if not price_col:
        raise RuntimeError("No suitable price column found")

    prices = work[price_col].astype(float).tolist()
    raw_signals = work[args.signal_col].fillna(0).astype(int).tolist()

    # Normalize to {-1, 0, 1}
    signals = [1 if s > 0 else (-1 if s < 0 else 0) for s in raw_signals]

    result = backtest_signals(
        prices=prices,
        signals=signals,
        initial_cash=args.initial_cash,
        commission_pct=args.commission_pct,
        slippage_pct=args.slippage_pct,
        position_size=args.position_size,
        constraints={
            "max_exposure_pct": args.max_exposure_pct,
            "max_position_units": args.max_position_units,
            "max_drawdown_pct": args.max_drawdown_pct,
            "trade_cooldown_bars": args.trade_cooldown_bars,
            "max_total_trades": args.max_total_trades,
            "flatten_on_risk_stop": True,
        },
    )

    print("Constrained backtest summary")
    print(f"- Symbol: {args.symbol or 'AUTO'}")
    print(f"- Price column: {price_col}")
    print(f"- Final balance: {result['final_balance']:.2f}")
    print(f"- Cumulative return: {result['cum_return']:.4f}")
    print(f"- Max drawdown: {result['max_drawdown']:.4f}")
    print(f"- Total trades: {len(result['trades'])}")
    print(f"- Risk stop triggered: {result['risk_stop_triggered']}")
    print(f"- Constraint events: {len(result['constraint_events'])}")

    if args.report_out:
        os.makedirs(os.path.dirname(args.report_out) or ".", exist_ok=True)
        with open(args.report_out, "w", encoding="utf-8") as handle:
            json.dump(result, handle, indent=2)
        print(f"- Report: {args.report_out}")


if __name__ == "__main__":
    main()
