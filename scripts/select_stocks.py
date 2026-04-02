"""CLI to score and select symbols for a given strategy using REAL market data.

Usage examples:
  python scripts/select_stocks.py --symbols BBCA TLKM --threshold 0.9
  python scripts/select_stocks.py
"""
import argparse

from src.ml.selector import score_symbols_for_strategy, select_high_confidence_symbols
from src.strategies.scalping import simple_sma_strategy


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--symbols",
        nargs="+",
        help="IDX symbols to score (real market data)",
        default=["BBCA", "TLKM", "BMRI", "ASII", "UNVR"],
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=0.9,
        help="Score threshold for selection",
    )
    args = parser.parse_args()

    print("🚀 Scoring symbols with REAL market data:", args.symbols)
    scored = score_symbols_for_strategy(
        args.symbols,
        simple_sma_strategy,
        allow_demo=False,  # Always use real data
    )
    for s, m in scored.items():
        if "error" in m:
            print(f"{s:6} ❌ ERROR: {m['error']}")
        else:
            print(
                f"{s:6} | Score: {m['score']:.3f} | Win Rate: {m['win_rate']:.1%} | "
                f"Trades: {m['num_trades']:2} | Balance: IDR {m['final_balance']:>12,.0f}"
            )

    selected = select_high_confidence_symbols(
        args.symbols,
        simple_sma_strategy,
        threshold=args.threshold,
        allow_demo=False,  # Always use real data
    )
    print(f"\n✅ Selected symbols (threshold={args.threshold}):")
    for s in selected:
        print(f"  • {s}")
    
    if not selected:
        print("  (No symbols met the threshold. Try lowering --threshold)")



if __name__ == "__main__":
    main()
