"""Generate demo price JSON files for offline testing.

Usage:
  python bin/runner.py scripts/generate_demo_prices.py -- --symbols BBCA.JK TLKM.JK --n 300
"""
from __future__ import annotations

import argparse
import json
import os
from typing import List

from src.demo import generate_price_series


def main(argv: List[str] | None = None):
    parser = argparse.ArgumentParser()
    parser.add_argument('--symbols', nargs='+', default=['BBCA.JK', 'TLKM.JK', 'BMRI.JK'])
    parser.add_argument('--n', type=int, default=200, help='Number of price points to generate')
    parser.add_argument('--out', default='data/prices', help='Output directory for JSON files')
    args = parser.parse_args(argv)

    os.makedirs(args.out, exist_ok=True)
    for s in args.symbols:
        prices = generate_price_series(n=args.n, start_price=100.0, volatility_pct=1.5)
        payload = {'symbol': s, 'prices': prices}
        fname = os.path.join(args.out, f"{s}.json")
        with open(fname, 'w', encoding='utf-8') as fh:
            json.dump(payload, fh)
        print('Wrote', fname)


if __name__ == '__main__':
    main()
