"""
Market Data Fetcher
===================
Realtime candlestick data from yfinance for multi-asset symbols.

Author: AutoSaham Team
Version: 1.0.0
"""

import heapq
import logging
import re
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Tuple
import yfinance as yf
import pandas as pd

logger = logging.getLogger(__name__)

# Forex/Crypto symbol metadata
MARKET_SYMBOLS = {
    'EURUSD=X': {'name': 'EUR/USD', 'sector': 'Forex'},
    'GBPUSD=X': {'name': 'GBP/USD', 'sector': 'Forex'},
    'USDJPY=X': {'name': 'USD/JPY', 'sector': 'Forex'},
    'AUDUSD=X': {'name': 'AUD/USD', 'sector': 'Forex'},
    'USDCHF=X': {'name': 'USD/CHF', 'sector': 'Forex'},
    'USDCAD=X': {'name': 'USD/CAD', 'sector': 'Forex'},
    'NZDUSD=X': {'name': 'NZD/USD', 'sector': 'Forex'},
    'EURJPY=X': {'name': 'EUR/JPY', 'sector': 'Forex'},
    'BTC-USD': {'name': 'Bitcoin', 'sector': 'Crypto'},
    'ETH-USD': {'name': 'Ethereum', 'sector': 'Crypto'},
    'SOL-USD': {'name': 'Solana', 'sector': 'Crypto'},
    'BNB-USD': {'name': 'BNB', 'sector': 'Crypto'},
    'XRP-USD': {'name': 'XRP', 'sector': 'Crypto'},
    'ADA-USD': {'name': 'Cardano', 'sector': 'Crypto'},
    'DOGE-USD': {'name': 'Dogecoin', 'sector': 'Crypto'},
}

# Timeframe mapping to yfinance periods
TIMEFRAME_MAP = {
    '1m': '1m',      # 1 minute
    '5m': '5m',      # 5 minutes
    '15m': '15m',    # 15 minutes
    '30m': '30m',    # 30 minutes
    '1h': '60m',     # 1 hour
    '4h': '1h',      # Will be aggregated to 4h
    '1d': '1d',      # 1 day
    '1w': '1wk',     # 1 week
    '1mo': '1mo',    # 1 month
}


async def fetch_candlesticks(
    symbol: str,
    timeframe: str = '1d',
    limit: int = 100,
    **kwargs
) -> Optional[Dict]:
    """
    Fetch candlestick data for a symbol.
    
    Args:
        symbol: Market symbol (e.g., 'EURUSD=X', 'BTC-USD')
        timeframe: Period (1m, 5m, 15m, 30m, 1h, 4h, 1d, 1w, 1mo)
        limit: Number of candles to fetch (max 500)
        
    Returns:
        Dict with candlesticks: {
            "symbol": "EURUSD=X",
            "timeframe": "1d",
            "candles": [
                {"time": 1696099200, "open": 10200, "high": 10300, "low": 10100, "close": 10250},
                ...
            ],
            "metadata": {
                "total": 100,
                "fetched_at": "2026-04-02T13:10:00Z",
                "exchange": "FOREX"
            }
        }
    """
    try:
        # Validate symbol
        if symbol not in MARKET_SYMBOLS:
            logger.warning(f"Symbol {symbol} not in MARKET_SYMBOLS list")
        
        # Map timeframe to yfinance format
        yf_interval = TIMEFRAME_MAP.get(timeframe, '1d')
        
        # Calculate period based on timeframe and limit
        period = _calculate_period(timeframe, limit)
        
        # Fetch data using yfinance
        logger.debug(f"Fetching {symbol} {timeframe} ({period})")
        ticker = yf.Ticker(symbol)
        
        # Fetch historical data with retries for timeframe-specific period constraints.
        df = _fetch_history_with_fallback(
            ticker=ticker,
            timeframe=timeframe,
            period=period,
            interval=yf_interval,
        )
        
        if df.empty:
            logger.warning(f"No data returned for {symbol}")
            return None
        
        # Ensure we have required columns
        required_columns = ['Open', 'High', 'Low', 'Close']
        if not all(col in df.columns for col in required_columns):
            logger.error(f"Missing OHLC columns for {symbol}")
            return None
        
        # Aggregate native 1h bars into true 4h bars.
        if timeframe == '4h':
            df = _aggregate_to_4h(df)

        # Convert to candlestick format
        candles = []
        for index, row in df.iterrows():
            # index is Timestamp, convert to Unix time
            timestamp = int(index.timestamp())
            
            candle = {
                "time": timestamp,
                "open": float(row['Open']),
                "high": float(row['High']),
                "low": float(row['Low']),
                "close": float(row['Close']),
            }
            
            # Add volume if available
            if 'Volume' in row and pd.notna(row['Volume']):
                candle["volume"] = int(row['Volume'])
            
            candles.append(candle)

        candles = _adaptive_sort_candles_by_time(candles)
        
        # Limit to requested count
        candles = candles[-limit:] if len(candles) > limit else candles
        
        upper_symbol = str(symbol or "").upper()
        currency, _ = _resolve_currency_profile(upper_symbol, info_currency=None)

        return {
            "symbol": symbol,
            "timeframe": timeframe,
            "candles": candles,
            "metadata": {
                "total": len(candles),
                "fetched_at": datetime.utcnow().isoformat() + "Z",
                "exchange": "FOREX" if symbol.upper().endswith('=X') else "CRYPTO" if "-USD" in symbol.upper() else "GLOBAL",
                "currency": currency,
                "source": "yfinance"
            }
        }
        
    except Exception as e:
        logger.error(f"Error fetching {symbol} candlesticks: {e}")
        return None


async def fetch_symbol_metadata(symbol: str) -> Optional[Dict]:
    """
    Get metadata for a symbol.
    
    Args:
        symbol: Market symbol (e.g., 'EURUSD=X', 'BTC-USD')
        
    Returns:
        Dict with symbol metadata
    """
    try:
        # Check if symbol exists in our list
        if symbol not in MARKET_SYMBOLS:
            logger.warning(f"Symbol {symbol} not found in MARKET_SYMBOLS")
            metadata = {"name": "Unknown", "sector": "Unknown"}
        else:
            metadata = MARKET_SYMBOLS[symbol].copy()
        
        # Fetch additional data from yfinance
        ticker = yf.Ticker(symbol)
        info = ticker.info if hasattr(ticker, 'info') else {}
        
        upper_symbol = str(symbol or "").upper()
        is_forex = upper_symbol.endswith('=X')
        is_crypto = '-USD' in upper_symbol

        exchange = "GLOBAL"
        if is_forex:
            exchange = "FOREX"
        elif is_crypto:
            exchange = "CRYPTO"

        info_currency = str(info.get("currency") or "").upper() or None
        currency, decimal_places = _resolve_currency_profile(upper_symbol, info_currency)
        timezone = "UTC"

        return {
            "symbol": symbol,
            "name": metadata.get("name", info.get("longName", "Unknown")),
            "exchange": exchange,
            "currency": currency,
            "decimalPlaces": decimal_places,
            "timezone": timezone,
            "sector": metadata.get("sector", info.get("sector", "Unknown")),
            "country": info.get("country", "Global"),
        }
        
    except Exception as e:
        logger.error(f"Error fetching metadata for {symbol}: {e}")
        return None


async def fetch_trading_status(market: Optional[str] = None, symbol: Optional[str] = None) -> Dict:
    """
    Get current trading status for Forex/Crypto markets.

    Returns:
        Dict with trading status
    """
    from datetime import datetime, timezone

    resolved_market = _resolve_market_type(market=market, symbol=symbol)
    now_utc = datetime.now(timezone.utc)

    if resolved_market == "crypto":
        return {
            "is_trading": True,
            "market": "crypto",
            "timezone": "UTC",
            "trading_hours": {
                "start": "00:00",
                "end": "23:59",
                "timezone": "UTC (24x7)",
            },
            "current_time": now_utc.isoformat(),
            "market_day": "OPEN_24_7",
            "next_open": None,
        }

    is_trading = _is_forex_open(now_utc)

    return {
        "is_trading": is_trading,
        "market": "forex",
        "timezone": "UTC",
        "trading_hours": {
            "start": "Sun 22:00",
            "end": "Fri 22:00",
            "timezone": "UTC (24x5)",
        },
        "current_time": now_utc.isoformat(),
        "market_day": "OPEN" if is_trading else "CLOSED",
        "next_open": None if is_trading else _get_next_forex_open(now_utc).isoformat(),
    }


async def get_available_symbols() -> List[str]:
    """Get list of available Forex/Crypto symbols."""
    return list(MARKET_SYMBOLS.keys())


# === Helper Functions ===

def _calculate_period(timeframe: str, limit: int) -> str:
    """Calculate yfinance period string based on timeframe and limit."""
    if timeframe == '1m':
        # yfinance supports 1m only for the latest 7 days.
        return '7d'
    elif timeframe in ['5m', '15m', '30m', '1h']:
        # For intraday >1m, yfinance supports up to 60 days.
        return '60d'
    elif timeframe == '4h':
        # Build 4h candles from 1h bars; fetch enough history for aggregation.
        return '180d'
    elif timeframe == '1d':
        # For daily, fetch ~2 years worth
        days = min(limit * 1.5, 730)  # 2 years max
        return f'{int(days)}d'
    elif timeframe == '1w':
        # yfinance weekly supports fixed period buckets only.
        if limit <= 8:
            return '3mo'
        if limit <= 16:
            return '6mo'
        if limit <= 52:
            return '1y'
        if limit <= 104:
            return '2y'
        if limit <= 260:
            return '5y'
        return '10y'
    elif timeframe == '1mo':
        # yfinance monthly supports fixed period buckets only.
        if limit <= 6:
            return '1y'
        if limit <= 12:
            return '2y'
        if limit <= 36:
            return '5y'
        return '10y'
    else:
        return '1y'


def _fetch_history_with_fallback(
    ticker,
    timeframe: str,
    period: str,
    interval: str,
) -> pd.DataFrame:
    """Fetch history with period fallbacks for provider-specific constraints."""
    candidates = [period]

    if timeframe == '1m':
        candidates.extend(['7d', '5d', '1d'])
    elif timeframe == '1w':
        candidates.extend(['1y', '2y', '5y'])
    elif timeframe == '1mo':
        candidates.extend(['2y', '5y', '10y'])

    seen = set()
    for candidate in candidates:
        if candidate in seen:
            continue
        seen.add(candidate)
        try:
            df = ticker.history(
                period=candidate,
                interval=interval,
                auto_adjust=False,
                actions=False,
            )
        except Exception as exc:
            logger.warning("History fetch failed for period %s: %s", candidate, exc)
            continue

        if not df.empty:
            return df

    return pd.DataFrame()


def _resolve_currency_profile(symbol: str, info_currency: Optional[str]) -> Tuple[str, int]:
    """Infer currency code and preferred decimal precision from symbol format."""
    upper = str(symbol or '').upper()

    if upper.endswith('=X'):
        pair = upper[:-2]
        if len(pair) == 6 and pair.isalpha():
            quote = pair[3:]
            if quote == 'JPY':
                return quote, 3
            if quote == 'IDR':
                return quote, 0
            return quote, 5
        return info_currency or 'USD', 5

    if '-' in upper:
        quote = upper.split('-')[-1]
        if re.fullmatch(r'[A-Z]{3}', quote):
            if quote == 'IDR':
                return quote, 0
            return quote, 2

    if info_currency and re.fullmatch(r'[A-Z]{3}', info_currency):
        if info_currency == 'IDR':
            return info_currency, 0
        return info_currency, 2

    return 'USD', 2


def _aggregate_to_4h(df: pd.DataFrame) -> pd.DataFrame:
    """Aggregate OHLCV dataframe into 4-hour bars."""
    if df.empty:
        return df

    agg_df = df.copy()
    if agg_df.index.tz is None:
        agg_df.index = agg_df.index.tz_localize('UTC')

    # Align bars to UTC market sessions for consistent chart rendering.
    agg_df.index = agg_df.index.tz_convert('UTC')

    rule = '4h'
    agg_map = {
        'Open': 'first',
        'High': 'max',
        'Low': 'min',
        'Close': 'last',
        'Volume': 'sum',
    }
    existing = {k: v for k, v in agg_map.items() if k in agg_df.columns}
    if not existing:
        return agg_df

    resampled = agg_df.resample(rule, label='right', closed='right').agg(existing).dropna()
    return resampled


def _adaptive_sort_candles_by_time(candles: List[Dict]) -> List[Dict]:
    """Adaptive sort: bubble for tiny sets, heap-sort style for larger sets."""
    n = len(candles)
    if n <= 1:
        return candles

    if n <= 20:
        # Bubble sort is acceptable and simple for tiny lists.
        sorted_candles = list(candles)
        for i in range(n):
            swapped = False
            for j in range(0, n - i - 1):
                left = int(sorted_candles[j].get('time') or 0)
                right = int(sorted_candles[j + 1].get('time') or 0)
                if left > right:
                    sorted_candles[j], sorted_candles[j + 1] = sorted_candles[j + 1], sorted_candles[j]
                    swapped = True
            if not swapped:
                break
        return sorted_candles

    heap = [(int(item.get('time') or 0), idx, item) for idx, item in enumerate(candles)]
    heapq.heapify(heap)
    output: List[Dict] = []
    while heap:
        output.append(heapq.heappop(heap)[2])
    return output


def _resolve_market_type(market: Optional[str], symbol: Optional[str]) -> str:
    market_text = str(market or "").strip().lower()
    if market_text in {"crypto", "blockchain"}:
        return "crypto"
    if market_text in {"forex", "fx"}:
        return "forex"

    upper_symbol = str(symbol or "").strip().upper()
    if "-USD" in upper_symbol or upper_symbol.endswith("USDT"):
        return "crypto"
    if upper_symbol.endswith("=X") or "/" in upper_symbol:
        return "forex"
    return "forex"


def _is_forex_open(current_time_utc: datetime) -> bool:
    weekday = current_time_utc.weekday()  # Mon=0, Sun=6
    hour = current_time_utc.hour

    if weekday in {0, 1, 2, 3}:
        return True
    if weekday == 4:
        return hour < 22
    if weekday == 6:
        return hour >= 22
    return False


def _get_next_forex_open(current_time_utc: datetime) -> datetime:
    weekday = current_time_utc.weekday()  # Mon=0, Sun=6
    hour = current_time_utc.hour

    if weekday == 6 and hour < 22:
        return current_time_utc.replace(hour=22, minute=0, second=0, microsecond=0)

    days_until_sunday = (6 - weekday) % 7
    base = current_time_utc + timedelta(days=days_until_sunday)
    return base.replace(hour=22, minute=0, second=0, microsecond=0)


async def verify_connectivity() -> bool:
    """Test connectivity to data source."""
    try:
        ticker = yf.Ticker('EURUSD=X')
        info = ticker.info
        return bool(info)
    except Exception as e:
        logger.error(f"Failed to verify connectivity: {e}")
        return False
