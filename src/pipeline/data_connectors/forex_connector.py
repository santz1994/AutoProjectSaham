"""Forex connector using exchangerate.host (no API key required).
"""


def fetch_forex_time_series(base='USD', symbols=None, start_date=None, end_date=None):
    symbols = symbols or ['IDR']
    try:
        import requests
    except Exception as e:
        raise RuntimeError('requests not installed; install with `pip install requests`') from e

    params = {
        'start_date': start_date or '',
        'end_date': end_date or '',
        'base': base,
        'symbols': ','.join(symbols),
    }
    url = 'https://api.exchangerate.host/timeseries'
    resp = requests.get(url, params=params, timeout=15)
    resp.raise_for_status()
    data = resp.json()

    # Best-effort validation of returned rates payload: ensure numeric series
    try:
        rates = data.get('rates') if isinstance(data, dict) else None
        if isinstance(rates, dict):
            # normalize symbols to list
            syms = symbols if isinstance(symbols, (list, tuple)) else [symbols]
            for s in syms:
                vals = []
                for d in sorted(rates.keys()):
                    row = rates.get(d)
                    if not isinstance(row, dict):
                        continue
                    # case-insensitive lookup for symbol
                    val = None
                    if s in row:
                        val = row[s]
                    elif s.upper() in row:
                        val = row[s.upper()]
                    else:
                        # fallback: first numeric-like value in the row
                        for v in row.values():
                            if isinstance(v, (int, float)) or (isinstance(v, str) and v.replace('.', '', 1).replace('-', '', 1).isdigit()):
                                val = v
                                break
                    if val is None:
                        continue
                    try:
                        vals.append(float(val))
                    except Exception:
                        # skip non-numeric entries
                        continue

                # validate collected series
                from .schemas import validate_price_series

                validate_price_series(vals)
    except Exception as e:
        raise RuntimeError(f'Forex data validation failed: {e}')

    return data
