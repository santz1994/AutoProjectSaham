"""CLI script: fetch price series for IDX listings in batches (rate-limited).

Example: `python scripts/fetch_idx_batch.py --limit 10`
"""
import os
import argparse

from src.pipeline.data_connectors.idx_listings import get_idx_listings
from src.pipeline.batch_fetcher import BatchFetcher


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--limit', type=int, default=10, help='Maximum symbols to fetch (default 10)')
    parser.add_argument('--period', type=str, default='1y', help='History period (e.g. 1y, 6mo)')
    parser.add_argument('--out', type=str, default='data/prices', help='Output folder for fetched JSON summaries')
    args = parser.parse_args()

    print('Fetching IDX listings...')
    try:
        items = get_idx_listings()
    except Exception as e:
        print('Failed to fetch IDX listings:', e)
        return

    symbols = []
    for it in items:
        if isinstance(it, dict):
            code = it.get('code') or it.get('symbol')
            if code:
                if not code.endswith('.JK'):
                    code = code + '.JK'
                symbols.append(code)

    if not symbols:
        print('No symbols available from IDX listings — falling back to sample list')
        symbols = ['BBCA.JK', 'TLKM.JK', 'BMRI.JK']

    fetcher = BatchFetcher(min_delay=1.0)
    results = fetcher.fetch_symbols(symbols, period=args.period, out_dir=args.out, limit=args.limit)

    ok = [r for r in results if r.get('status') == 'ok']
    err = [r for r in results if r.get('status') == 'error']
    print(f'Completed: {len(ok)} ok, {len(err)} errors')
    for e in err[:10]:
        print('ERR', e['symbol'], e.get('error'))


if __name__ == '__main__':
    main()
