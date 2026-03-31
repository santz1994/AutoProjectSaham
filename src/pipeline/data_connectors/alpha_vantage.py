"""Simple Alpha Vantage adapter for daily adjusted time series.

Requires an API key (set `ALPHA_VANTAGE_KEY` in the environment).
"""
from typing import List


def fetch_daily_adjusted(
    symbol: str, api_key: str, outputsize: str = "compact", timeout: int = 15
) -> List[float]:
    try:
        import requests
    except Exception as e:
        raise RuntimeError(
            "requests not installed; install with `pip install requests`"
        ) from e

    url = "https://www.alphavantage.co/query"
    params = {
        "function": "TIME_SERIES_DAILY_ADJUSTED",
        "symbol": symbol,
        "outputsize": outputsize,
        "apikey": api_key,
    }
    resp = requests.get(url, params=params, timeout=timeout)
    if resp.status_code != 200:
        raise RuntimeError(f"AlphaVantage request failed: status={resp.status_code}")

    data = resp.json()
    # time series key
    ts_key = None
    for k in ("Time Series (Daily)", "Time Series"):
        if k in data:
            ts_key = k
            break

    if ts_key is None:
        # if message present, include it
        if "Note" in data:
            raise RuntimeError(
                "AlphaVantage error: " + data.get("Note", "rate limit or API issue")
            )
        if "Error Message" in data:
            raise RuntimeError(
                "AlphaVantage error: " + data.get("Error Message", "unknown")
            )
        raise RuntimeError("AlphaVantage: unexpected response format")

    series = data[ts_key]
    # series is dict keyed by date descending; we need chronological list
    dates = sorted(series.keys())
    prices = []
    for d in dates:
        item = series[d]
        # adjusted close key name in AV JSON
        adj = item.get("5. adjusted close") or item.get("4. close")
        try:
            prices.append(float(adj))
        except Exception:
            continue

    if not prices:
        raise RuntimeError("AlphaVantage returned no numeric prices")

    # validate series before returning
    try:
        from .schemas import validate_price_series

        validate_price_series(prices)
    except Exception:
        # re-raise as runtime error to give connectors a clear failure
        raise

    return prices
