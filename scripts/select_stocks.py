"""CLI to score and select symbols for a given strategy.

Usage examples:
  python scripts/select_stocks.py --symbols BBCA.JK TLKM.JK --threshold 0.9
  python scripts/select_stocks.py --demo
"""
import argparse

from src.ml.selector import score_symbols_for_strategy, select_high_confidence_symbols
from src.strategies.scalping import simple_sma_strategy


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--symbols",
        nargs="+",
        help="Symbols to score",
        default=["BBCA.JK", "TLKM.JK", "BMRI.JK"],
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=0.9,
        help="Score threshold for selection",
    )
    parser.add_argument(
        "--demo",
        action="store_true",
        help="Force demo price generation (no yfinance)",
    )
    args = parser.parse_args()

    print("Scoring symbols:", args.symbols)
    scored = score_symbols_for_strategy(
        args.symbols,
        simple_sma_strategy,
        allow_demo=args.demo,
    )
    for s, m in scored.items():
        if "error" in m:
            print(s, "ERROR:", m["error"])
        else:
            print(
                f"{s}: score={m['score']:.3f} "
                f"win_rate={m['win_rate']:.2f} "
                f"trades={m['num_trades']} "
                f"final_bal={m['final_balance']:.2f}"
            )

    selected = select_high_confidence_symbols(
        args.symbols,
        simple_sma_strategy,
        threshold=args.threshold,
        allow_demo=args.demo,
    )
    print("\nSelected symbols (threshold=%s):" % args.threshold)
    for s in selected:
        print("-", s)


if __name__ == "__main__":
    main()
