"""Batch fetcher to download historical prices for many symbols.

Uses `YahooFetcher` under the hood and writes per-symbol JSON summaries
to `data/prices/` by default. Designed for sequential, rate-limited fetching.
"""
from __future__ import annotations

import json
import os
import time
from typing import List, Dict


def _ensure_dir(path: str):
    os.makedirs(path, exist_ok=True)


class BatchFetcher:
    def __init__(self, cache_db: str | None = None, min_delay: float = 1.0):
        from .data_connectors.yahoo_fetcher import YahooFetcher

        self.fetcher = YahooFetcher(cache_db=cache_db, min_delay=min_delay)

    def fetch_symbols(
        self,
        symbols: List[str],
        period: str = '1y',
        out_dir: str = 'data/prices',
        limit: int | None = None,
        force_refresh: bool = False,
    ) -> List[Dict]:
        _ensure_dir(out_dir)
        results: List[Dict] = []
        i = 0
        for sym in symbols:
            if limit is not None and i >= limit:
                break
            i += 1
            try:
                prices = self.fetcher.fetch(
                    sym,
                    period=period,
                    use_cache=not force_refresh,
                    force_refresh=force_refresh,
                )
                fname = os.path.join(out_dir, f'{sym}.json')
                with open(fname, 'w', encoding='utf-8') as fh:
                    json.dump(
                        {
                            'symbol': sym,
                            'prices_count': len(prices),
                            'prices': prices,
                            'fetched_at': int(time.time()),
                        },
                        fh,
                        ensure_ascii=False,
                    )
                results.append({
                    'symbol': sym,
                    'status': 'ok',
                    'count': len(prices),
                    'file': fname,
                })
            except Exception as e:
                results.append({
                    'symbol': sym,
                    'status': 'error',
                    'error': str(e),
                })

        return results
