"""Run the selector across IDX listings using REAL market data.

This script retrieves all IDX-listed stocks and scores them using the SMA strategy
with real historical market data from Yahoo Finance.
"""
from src.ml.selector import score_symbols_for_strategy
from src.pipeline.data_connectors.idx_listings import get_idx_listings
from src.strategies.scalping import simple_sma_strategy


def main():
    print("📊 Fetching IDX listings...")
    try:
        items = get_idx_listings()
    except Exception as e:
        print(f"⚠️  Failed to fetch IDX listings: {e}")
        print("Using top 20 IDX symbols instead...")
        items = [{"code": s} for s in ["BBCA", "USIM", "KLBF", "ASII", "UNVR", "GOTO", "MAPI", "PROL", "TKIM", "INDX", 
                                        "PTBA", "WIKA", "SCMA", "INTP", "SMGR", "PGAS", "TLKM", "ADRO", "INDY", "MEDC"]]

    codes = []
    for it in items:
        code = it.get("code") if isinstance(it, dict) else None
        if code:
            # Remove .JK suffix if present, we'll add it later if needed
            if code.endswith(".JK"):
                codes.append(code[:-3])
            else:
                codes.append(code)

    if not codes:
        print("❌ No IDX symbols available. Exiting.")
        return

    print(f"🚀 Scoring {len(codes)} real IDX symbols with actual market data...")
    print("   (This may take several minutes for full IDX list. Using real Yahoo Finance data.)\n")
    
    scored = score_symbols_for_strategy(
        codes,
        simple_sma_strategy,
        period="1y",
        allow_demo=False,  # ALWAYS use real data, no demo fallback
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
            print(f"{s:8} | {score:>6.3f} | {win_rate:>8.1%} | {trades:>6} | IDR {balance:>11,.0f}")
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
