"""Robust Yahoo Finance CSV fetcher with local SQLite cache and retries.

Features:
- Uses `requests` with urllib3 Retry for resilient HTTP calls.
- Simple per-instance rate-limiting (`min_delay`) to avoid bursts.
- Local SQLite cache stored at `data/yahoo_cache.db` by default.
- Safe CSV parsing using Python's `csv` module.

Use `YahooFetcher().fetch(symbol, period='1y')` to get a list of historical
adjusted-close prices in chronological order.
"""
from __future__ import annotations

import csv
import io
import os
import sqlite3
import time
from typing import List
from .schemas import validate_price_series

try:
    import requests
    from requests.adapters import HTTPAdapter
    from urllib3.util.retry import Retry
except Exception:  # pragma: no cover - runtime error messaging handled below
    requests = None


class YahooFetcher:
    def __init__(
        self,
        cache_db: str | None = None,
        min_delay: float = 1.0,
        timeout: int = 30,
        retries: int = 3,
        backoff_factor: float = 0.5,
    ):
        if requests is None:
            raise RuntimeError(
                'requests and urllib3 are required for YahooFetcher; install with `pip install requests`'
            )

        self.cache_db = cache_db or os.path.join(os.getcwd(), 'data', 'yahoo_cache.db')
        os.makedirs(os.path.dirname(self.cache_db), exist_ok=True)
        self.min_delay = float(min_delay)
        self.timeout = int(timeout)
        self._last_request = 0.0

        # HTTP session with retry/backoff
        self.session = requests.Session()
        retry = Retry(
            total=retries,
            backoff_factor=backoff_factor,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=frozenset(['GET']),
        )
        adapter = HTTPAdapter(max_retries=retry)
        self.session.mount('https://', adapter)
        self.session.headers.update({'User-Agent': 'AutoSaham/1.0 (+https://github.com)'})

        # DB connection
        self._conn = sqlite3.connect(self.cache_db, check_same_thread=False)
        self._ensure_db()

    def _ensure_db(self):
        cur = self._conn.cursor()
        cur.execute(
            '''CREATE TABLE IF NOT EXISTS price_cache (
                   symbol TEXT NOT NULL,
                   period TEXT NOT NULL,
                   fetched_at INTEGER NOT NULL,
                   csv TEXT,
                   PRIMARY KEY(symbol, period)
               )'''
        )
        self._conn.commit()

    def _get_cached(self, symbol: str, period: str, ttl: int):
        cur = self._conn.cursor()
        cur.execute('SELECT fetched_at, csv FROM price_cache WHERE symbol=? AND period=?', (symbol, period))
        row = cur.fetchone()
        if not row:
            return None
        fetched_at, csv_text = row
        if int(time.time()) - int(fetched_at) > int(ttl):
            return None
        return csv_text

    def _set_cache(self, symbol: str, period: str, csv_text: str):
        cur = self._conn.cursor()
        cur.execute('INSERT OR REPLACE INTO price_cache(symbol, period, fetched_at, csv) VALUES(?,?,?,?)', (symbol, period, int(time.time()), csv_text))
        self._conn.commit()

    def _sleep_if_needed(self):
        elapsed = time.time() - self._last_request
        if elapsed < self.min_delay:
            time.sleep(self.min_delay - elapsed)

    def fetch(self, symbol: str, period: str = '1y', use_cache: bool = True, cache_ttl: int = 60 * 60 * 24, force_refresh: bool = False) -> List[float]:
        """Fetch historical adjusted-close prices for `symbol`.

        symbol: ticker string (e.g. 'BBCA.JK' or 'AAPL')
        period: simple string like '1y' or '6mo'
        use_cache: if True, will return cached CSV within `cache_ttl` seconds
        force_refresh: ignore cache and fetch anew
        """
        if use_cache and not force_refresh:
            cached = self._get_cached(symbol, period, cache_ttl)
            if cached:
                return self._parse_csv_to_prices(cached)

        # compute unix timestamps for period
        from datetime import datetime, timedelta, timezone
        end_dt = datetime.now(timezone.utc)
        days = 365
        if isinstance(period, str):
            if period.endswith('y'):
                try:
                    years = int(period[:-1]) if period[:-1] else 1
                    days = years * 365
                except Exception:
                    days = 365
            elif period.endswith('mo'):
                try:
                    months = int(period[:-2]) if period[:-2] else 6
                    days = months * 30
                except Exception:
                    days = 183

        start_dt = end_dt - timedelta(days=days)
        import calendar as _calendar
        period1 = int(_calendar.timegm(start_dt.utctimetuple()))
        period2 = int(_calendar.timegm(end_dt.utctimetuple()))

        url = (
            f'https://query1.finance.yahoo.com/v7/finance/download/{symbol}'
            f'?period1={period1}&period2={period2}&interval=1d&events=history&includeAdjustedClose=true'
        )

        self._sleep_if_needed()
        resp = self.session.get(url, timeout=self.timeout)
        self._last_request = time.time()

        if resp.status_code != 200:
            # some Yahoo CSV endpoints now require authentication/crumbs; fall back to yfinance
            try:
                import yfinance as yf
                df = yf.download(symbol, period=period, interval='1d', progress=False)
                if df is not None and not df.empty:
                    # handle both single- and multi-index columns robustly
                    try:
                        if 'Adj Close' in df.columns:
                            series = df['Adj Close']
                        elif 'Close' in df.columns:
                            series = df['Close']
                        else:
                            # multiindex columns (e.g., ('Close', 'AAPL'))
                            found = None
                            for col in df.columns:
                                if isinstance(col, tuple) and col[0] in ('Adj Close', 'Close'):
                                    found = col
                                    break
                            if found is not None:
                                series = df[found]
                            else:
                                # fallback to last column
                                series = df.iloc[:, -1]

                        # series may be a DataFrame (if multiple tickers), select first column
                        if hasattr(series, 'shape') and getattr(series, 'ndim', 1) > 1:
                            # pick first column
                            series = series.iloc[:, 0]

                        vals = [float(x) for x in series.tolist()]
                        # validate the series before returning
                        validate_price_series(vals)
                        return vals
                    except Exception:
                        # if selection/parsing fails, allow outer handler to raise
                        pass
            except Exception:
                # continue to raise the original error below
                pass

            raise RuntimeError(f'Yahoo CSV fetch failed for {symbol}: status={resp.status_code} body={resp.text[:300]}')

        csv_text = resp.text
        prices = self._parse_csv_to_prices(csv_text)
        # validate parsed series before returning
        validate_price_series(prices)

        # cache best-effort
        try:
            self._set_cache(symbol, period, csv_text)
        except Exception:
            pass

        return prices

    def _parse_csv_to_prices(self, csv_text: str) -> List[float]:
        f = io.StringIO(csv_text)
        reader = csv.reader(f)
        rows = list(reader)
        if not rows:
            raise RuntimeError('Empty CSV returned from Yahoo')

        header = rows[0]
        try:
            adj_idx = header.index('Adj Close') if 'Adj Close' in header else header.index('Close')
        except ValueError:
            raise RuntimeError('Unexpected CSV format from Yahoo')

        prices: List[float] = []
        for row in rows[1:]:
            if len(row) <= adj_idx:
                continue
            val = row[adj_idx]
            if val in ('', 'null', 'NA'):
                continue
            try:
                prices.append(float(val))
            except Exception:
                continue

        if not prices:
            raise RuntimeError('No numeric prices parsed from Yahoo CSV')

        return prices

    def clear_cache(self):
        cur = self._conn.cursor()
        cur.execute('DELETE FROM price_cache')
        self._conn.commit()

    def close(self):
        try:
            if getattr(self, '_conn', None):
                try:
                    self._conn.close()
                except Exception:
                    pass
        except Exception:
            pass

    def __del__(self):
        try:
            self.close()
        except Exception:
            pass
