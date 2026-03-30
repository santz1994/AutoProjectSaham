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
    return resp.json()
