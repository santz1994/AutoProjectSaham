"""Run the selector across a Forex/Crypto watchlist using real market data."""
from src.ml.selector import score_symbols_for_strategy
from src.strategies.scalping import simple_sma_strategy


def main():
    symbols = [
        "EURUSD=X",
        "GBPUSD=X",
        "USDJPY=X",
        "AUDUSD=X",
        "BTC-USD",
        "ETH-USD",
        "SOL-USD",
        "BNB-USD",
        "XRP-USD",
        "ADA-USD",
    ]

    print(f"🚀 Scoring {len(symbols)} Forex/Crypto symbols with real market data...")
    print("   (Using Yahoo Finance data source.)\n")

    scored = score_symbols_for_strategy(
        symbols,
        simple_sma_strategy,
        period="1y",
        allow_demo=False,
    )

    # Select with 0.9 threshold
    selected = [
        s for s, m in scored.items() if isinstance(m, dict) and m.get("score", 0) >= 0.9
    ]
    print(f"\n✅ Selected {len(selected)} symbols with score >= 0.9")
    if selected:
        print("\nTop 20 selections (by score):")
        print("─" * 60)
        print(f"{'Symbol':8} | {'Score':>6} | {'Win Rate':>9} | {'Trades':>6} | {'Balance':>13}")
        print("─" * 60)
        
        sorted_selected = sorted(
            [(s, scored[s]) for s in selected],
            key=lambda x: x[1].get("score", 0),
            reverse=True
        )
        
        for s, m in sorted_selected[:20]:
            score = m.get('score', 0)
            win_rate = m.get('win_rate', 0)
            trades = m.get('num_trades', 0)
            balance = m.get('final_balance', 0)
            print(f"{s:10} | {score:>6.3f} | {win_rate:>8.1%} | {trades:>6} | {balance:>13,.2f}")
        print("─" * 60)
    else:
        print("\n⚠️  No symbols reached the 0.9 threshold.")
        print("Top 10 by score:")
        print("─" * 60)
        sorted_scored = sorted(
            [(s, m) for s, m in scored.items() if isinstance(m, dict)],
            key=lambda x: x[1].get("score", 0),
            reverse=True
        )
        for s, m in sorted_scored[:10]:
            score = m.get('score', 0)
            win_rate = m.get('win_rate', 0)
            trades = m.get('num_trades', 0)
            print(f"{s:8} | Score: {score:.3f} | Win Rate: {win_rate:>8.1%} | Trades: {trades}")



if __name__ == "__main__":
    main()
