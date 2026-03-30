"""Run the selector across IDX listings using demo price fallback.

This is a demo run: if real market data isn't available the script will
generate synthetic price series so the selection pipeline can be exercised.
"""
from src.pipeline.data_connectors.idx_listings import get_idx_listings
from src.ml.selector import score_symbols_for_strategy, select_high_confidence_symbols
from src.strategies.scalping import simple_sma_strategy


def main():
    print('Collecting IDX tickers (best-effort)...')
    try:
        items = get_idx_listings()
    except Exception as e:
        print('Failed to fetch IDX listings:', e)
        items = []

    codes = []
    for it in items:
        code = it.get('code') if isinstance(it, dict) else None
        if code:
            if code.endswith('.JK'):
                codes.append(code)
            else:
                codes.append(code + '.JK')

    if not codes:
        # fallback: run a smaller demo set
        codes = [f'DEMO{i+1}' for i in range(200)]

    print(f'Running scorer on {len(codes)} symbols (demo fallback ON). This may take a moment...')
    scored = score_symbols_for_strategy(codes, simple_sma_strategy, period='1y', allow_demo=True)

    # select with 0.9 threshold
    selected = [s for s, m in scored.items() if isinstance(m, dict) and m.get('score', 0) >= 0.9]
    print(f'Selected {len(selected)} symbols with score >= 0.9')
    if selected:
        print('Top selections (sample):')
        for s in selected[:20]:
            m = scored[s]
            print(f"{s}: score={m.get('score'):.3f} win_rate={m.get('win_rate'):.2f} trades={m.get('num_trades')}")
    else:
        print('No symbols reached the 0.9 threshold in this demo run.')


if __name__ == '__main__':
    main()
