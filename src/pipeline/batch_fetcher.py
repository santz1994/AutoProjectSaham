"""Batch fetcher to download historical prices for many symbols.

Uses `HFFetcher` (CCXT-based) or fallback data sources under the hood
and writes per-symbol JSON summaries to `data/prices/` by default.
Designed for sequential, rate-limited fetching.
"""
from __future__ import annotations

import json
import os
import time
from typing import Dict, List


def _ensure_dir(path: str):
    os.makedirs(path, exist_ok=True)


class BatchFetcher:
    def __init__(self, cache_db: str | None = None, min_delay: float = 1.0):
        self.min_delay = min_delay
        self._use_hf = False
        try:
            from .data_connectors import hf_connector as _hf
            self._hf_module = _hf
            self._use_hf = True
        except Exception:
            self._hf_module = None

    def _hf_fetch(self, symbol: str, timeframe: str = "5m", candles: int = 288) -> List[Dict]:
        """Adapter: use hf_connector to fetch OHLCV data and return list of dicts."""
        if not self._use_hf or self._hf_module is None:
            raise RuntimeError("No data connector available (ccxt not installed)")
        df = self._hf_module.fetch_historical_data(
            exchange_id="binance",
            symbol=symbol,
            timeframe=timeframe,
            candles=candles,
            strict=False,
        )
        records = df.to_dict("records")
        for r in records:
            if "datetime" in r and hasattr(r["datetime"], "isoformat"):
                r["datetime"] = r["datetime"].isoformat()
        return records

    def fetch_symbols(
        self,
        symbols: List[str],
        period: str = "1y",
        out_dir: str = "data/prices",
        limit: int | None = None,
        force_refresh: bool = False,
    ) -> List[Dict]:
        _ensure_dir(out_dir)
        results: List[Dict] = []
        # Map period string to approximate candle count for 5m timeframe
        _period_candles = {
            "1d": 288, "1w": 2016, "1m": 8640, "3m": 25920,
            "6m": 51840, "1y": 103680, "2y": 207360,
        }
        candles = _period_candles.get(period, 288)
        i = 0
        for sym in symbols:
            if limit is not None and i >= limit:
                break
            i += 1
            try:
                # Convert Yahoo-style symbol to CCXT format
                ccxt_sym = sym.replace("=X", "").replace("USD", "/USD")
                if "-" in sym:
                    ccxt_sym = sym.replace("-", "/")
                prices = self._hf_fetch(ccxt_sym, timeframe="5m", candles=candles)
                fname = os.path.join(out_dir, f"{sym}.json")
                with open(fname, "w", encoding="utf-8") as fh:
                    json.dump(
                        {
                            "symbol": sym,
                            "prices_count": len(prices),
                            "prices": prices,
                            "fetched_at": int(time.time()),
                        },
                        fh,
                        ensure_ascii=False,
                    )
                results.append(
                    {
                        "symbol": sym,
                        "status": "ok",
                        "count": len(prices),
                        "file": fname,
                    }
                )
            except Exception as e:
                results.append(
                    {
                        "symbol": sym,
                        "status": "error",
                        "error": str(e),
                    }
                )

        return results
