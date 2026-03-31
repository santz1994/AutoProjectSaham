"""IDX / stock connector (placeholder).

This attempts to use `yfinance` when available. For real IDX integration use your
broker's market data API or a dedicated market-data provider.
"""


def fetch_idx(symbols, start_date=None, end_date=None):
    """Fetch historical price tables for given IDX tickers.

    symbols: list of tickers (e.g. ['BBCA', 'TLKM']) — function will append '.JK'
    if required for yfinance.
    """
    try:
        import yfinance as yf
    except Exception as e:
        raise RuntimeError('yfinance not installed; install with `pip install yfinance`') from e

    tickers = [s if s.endswith('.JK') else f"{s}.JK" for s in symbols]
    out = {}
    for t in tickers:
        df = yf.download(t, start=start_date, end=end_date, progress=False)
        # validate OHLCV-like rows when pandas DataFrame is returned
        try:
            if df is not None and not df.empty:
                # ensure index (date) is included in records
                try:
                    recs = df.reset_index().to_dict('records')
                except Exception:
                    # fallback: try to coerce to list of dicts
                    recs = [dict(r) for r in getattr(df, 'to_dict', lambda: [])()]
                from .schemas import validate_ohlcv_rows

                validate_ohlcv_rows(recs)
        except Exception as e:
            raise RuntimeError(f'Validation failed for {t}: {e}')

        out[t] = df
    return out
