"""Fetch and cache REAL historical prices from Yahoo Finance for offline use.

This replaces the old mock price generation with real market data caching.

Usage:
    python bin/runner.py scripts/generate_demo_prices.py -- \\
        --symbols BBCA TLKM USIM --n 300
"""
from __future__ import annotations

import argparse
import json
import os
from typing import List

from src.pipeline.data_connectors.yahoo_fetcher import YahooFetcher


def main(argv: List[str] | None = None):
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--symbols",
        nargs="+",
        default=["BBCA", "TLKM", "USIM", "BMRI", "ASII"],
        help="IDX symbols to fetch (real Yahoo Finance data)",
    )
    parser.add_argument(
        "--period",
        default="1y",
        help="Period for Yahoo Finance (1mo, 3mo, 1y, 2y, etc.)",
    )
    parser.add_argument(
        "--out",
        default="data/prices",
        help="Output directory for cached JSON files",
    )
    parser.add_argument(
        "--n",
        type=int,
        default=None,
        help="Optional maximum number of candles to keep (backward compatible)",
    )
    args = parser.parse_args(argv)

    os.makedirs(args.out, exist_ok=True)
    
    fetcher = YahooFetcher(min_delay=0.5)
    
    for symbol in args.symbols:
        try:
            print(f"Fetching {symbol} ({args.period})...", end=" ")
            prices = fetcher.fetch(symbol, period=args.period, use_cache=False, force_refresh=True)

            if args.n and args.n > 0:
                prices = prices[-args.n:]
            
            if not prices:
                print("❌ No data")
                continue
            
            payload = {
                "symbol": symbol,
                "period": args.period,
                "count": len(prices),
                "prices": prices
            }
            
            fname = os.path.join(args.out, f"{symbol}.json")
            with open(fname, "w", encoding="utf-8") as fh:
                json.dump(payload, fh, indent=2)
            
            print(f"✅ {len(prices)} candles -> {fname}")
            
        except Exception as e:
            print(f"❌ Error: {e}")


if __name__ == "__main__":
    main()

