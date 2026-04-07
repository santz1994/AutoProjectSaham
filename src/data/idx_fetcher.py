"""
IDX/BEI Stock Data Fetcher
============================
Real-time candlestick data from Indonesia Stock Exchange (IDX/BEI)
using yfinance with curl_cffi for rate limiting bypass.

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

# IDX Symbol metadata
IDX_SYMBOLS = {
    'BBCA.JK': {'name': 'Bank Central Asia', 'sector': 'Financial Services'},
    'USIM.JK': {'name': 'United US Steel', 'sector': 'Mining'},
    'KLBF.JK': {'name': 'Kalbe Farma', 'sector': 'Healthcare'},
    'ASII.JK': {'name': 'Astra International', 'sector': 'Automotive'},
    'UNVR.JK': {'name': 'Unilever Indonesia', 'sector': 'Consumer Goods'},
    'INDF.JK': {'name': 'Indofood Sukses Makmur', 'sector': 'Consumer Goods'},
    'PGAS.JK': {'name': 'Perusahaan Gas Negara', 'sector': 'Energy'},
    'GGRM.JK': {'name': 'Gudang Garam', 'sector': 'Consumer Goods'},
    'TLKM.JK': {'name': 'Telekomunikasi Indonesia', 'sector': 'Telecommunications'},
    'SMGR.JK': {'name': 'Semen Indonesia', 'sector': 'Mining'},
    'BMRI.JK': {'name': 'Bank Mandiri', 'sector': 'Financial Services'},
    'BBRI.JK': {'name': 'Bank Rakyat Indonesia', 'sector': 'Financial Services'},
    'BBNI.JK': {'name': 'Bank Negara Indonesia', 'sector': 'Financial Services'},
    'BBTN.JK': {'name': 'Bank Tabungan Negara', 'sector': 'Financial Services'},
    'ADRO.JK': {'name': 'Adaro Energy', 'sector': 'Energy'},
    'ANTM.JK': {'name': 'Aneka Tambang', 'sector': 'Mining'},
    'BRIS.JK': {'name': 'Bank Syariah Indonesia', 'sector': 'Financial Services'},
    'CPIN.JK': {'name': 'Charoen Pokphand Indonesia', 'sector': 'Consumer Goods'},
    'EXCL.JK': {'name': 'XL Axiata', 'sector': 'Telecommunications'},
    'ICBP.JK': {'name': 'Indofood CBP', 'sector': 'Consumer Goods'},
    'INCO.JK': {'name': 'Vale Indonesia', 'sector': 'Mining'},
    'INKP.JK': {'name': 'Indah Kiat Pulp & Paper', 'sector': 'Industrials'},
    'ISAT.JK': {'name': 'Indosat Ooredoo Hutchison', 'sector': 'Telecommunications'},
    'JSMR.JK': {'name': 'Jasa Marga', 'sector': 'Infrastructure'},
    'MDKA.JK': {'name': 'Merdeka Copper Gold', 'sector': 'Mining'},
    'MEDC.JK': {'name': 'Medco Energi', 'sector': 'Energy'},
    'MNCN.JK': {'name': 'Media Nusantara Citra', 'sector': 'Media'},
    'PTBA.JK': {'name': 'Bukit Asam', 'sector': 'Energy'},
    'SCMA.JK': {'name': 'Surya Citra Media', 'sector': 'Media'},
    'SIDO.JK': {'name': 'Industri Jamu Sido Muncul', 'sector': 'Healthcare'},
    'TBIG.JK': {'name': 'Tower Bersama Infrastructure', 'sector': 'Infrastructure'},
    'TPIA.JK': {'name': 'Chandra Asri Pacific', 'sector': 'Chemicals'},
    'WIKA.JK': {'name': 'Wijaya Karya', 'sector': 'Infrastructure'},
    'AMRT.JK': {'name': 'Sumber Alfaria Trijaya', 'sector': 'Consumer Goods'},
    'AKRA.JK': {'name': 'AKR Corporindo', 'sector': 'Industrials'},
    'ERAA.JK': {'name': 'Erajaya Swasembada', 'sector': 'Consumer Cyclical'},
    'GOTO.JK': {'name': 'GoTo Gojek Tokopedia', 'sector': 'Technology'},
    'HRUM.JK': {'name': 'Harum Energy', 'sector': 'Energy'},
    'ITMG.JK': {'name': 'Indo Tambangraya Megah', 'sector': 'Energy'},
    'MAPI.JK': {'name': 'Mitra Adiperkasa', 'sector': 'Consumer Cyclical'},
    'PGEO.JK': {'name': 'Pertamina Geothermal Energy', 'sector': 'Energy'},
    'SRTG.JK': {'name': 'Saratoga Investama Sedaya', 'sector': 'Financial Services'},
    'UNTR.JK': {'name': 'United Tractors', 'sector': 'Industrials'},
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
    Fetch candlestick data from IDX for a symbol.
    
    Args:
        symbol: IDX symbol (e.g., 'BBCA.JK')
        timeframe: Period (1m, 5m, 15m, 30m, 1h, 4h, 1d, 1w, 1mo)
        limit: Number of candles to fetch (max 500)
        
    Returns:
        Dict with candlesticks: {
            "symbol": "BBCA.JK",
            "timeframe": "1d",
            "candles": [
                {"time": 1696099200, "open": 10200, "high": 10300, "low": 10100, "close": 10250},
                ...
            ],
            "metadata": {
                "total": 100,
                "fetched_at": "2026-04-02T13:10:00Z",
                "exchange": "IDX"
            }
        }
    """
    try:
        # Validate symbol
        if symbol not in IDX_SYMBOLS:
            logger.warning(f"Symbol {symbol} not in IDX_SYMBOLS list")
        
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
                "exchange": "IDX" if symbol.upper().endswith('.JK') else "GLOBAL",
                "currency": currency,
                "source": "yfinance"
            }
        }
        
    except Exception as e:
        logger.error(f"Error fetching {symbol} candlesticks: {e}")
        return None


async def fetch_symbol_metadata(symbol: str) -> Optional[Dict]:
    """
    Get metadata for an IDX symbol.
    
    Args:
        symbol: IDX symbol (e.g., 'BBCA.JK')
        
    Returns:
        Dict with symbol metadata
    """
    try:
        # Check if symbol exists in our list
        if symbol not in IDX_SYMBOLS:
            logger.warning(f"Symbol {symbol} not found in IDX_SYMBOLS")
            metadata = {"name": "Unknown", "sector": "Unknown"}
        else:
            metadata = IDX_SYMBOLS[symbol].copy()
        
        # Fetch additional data from yfinance
        ticker = yf.Ticker(symbol)
        info = ticker.info if hasattr(ticker, 'info') else {}
        
        upper_symbol = str(symbol or "").upper()
        is_idx = upper_symbol.endswith('.JK')
        is_forex = upper_symbol.endswith('=X')
        is_crypto = '-USD' in upper_symbol

        exchange = "IDX" if is_idx else "GLOBAL"
        if is_forex:
            exchange = "FOREX"
        elif is_crypto:
            exchange = "CRYPTO"

        info_currency = str(info.get("currency") or "").upper() or None
        currency, decimal_places = _resolve_currency_profile(upper_symbol, info_currency)
        timezone = "Asia/Jakarta" if is_idx else "UTC"

        return {
            "symbol": symbol,
            "name": metadata.get("name", info.get("longName", "Unknown")),
            "exchange": exchange,
            "currency": currency,
            "decimalPlaces": decimal_places,
            "timezone": timezone,
            "sector": metadata.get("sector", info.get("sector", "Unknown")),
            "country": "Indonesia" if is_idx else info.get("country", "Global"),
        }
        
    except Exception as e:
        logger.error(f"Error fetching metadata for {symbol}: {e}")
        return None


async def fetch_trading_status() -> Dict:
    """
    Get current IDX trading status.
    
    IDX Trading Hours:
    - Monday - Friday: 09:00 - 16:00 WIB (UTC+7)
    - Saturday, Sunday: Closed
    
    Returns:
        Dict with trading status
    """
    from datetime import datetime, timezone, timedelta
    
    # Jakarta timezone (UTC+7)
    jakarta_tz = timezone(timedelta(hours=7))
    now = datetime.now(jakarta_tz)
    
    # Trading hours: 09:00 - 16:00 WIB (09:00 - 16:00 UTC+7)
    trading_start = now.replace(hour=9, minute=0, second=0, microsecond=0)
    trading_end = now.replace(hour=16, minute=0, second=0, microsecond=0)
    
    # Check if today is a trading day (Mon-Fri)
    is_trading_day = now.weekday() < 5  # 0-4 = Mon-Fri
    
    # Check if currently within trading hours
    is_trading = is_trading_day and (trading_start <= now <= trading_end)
    
    return {
        "is_trading": is_trading,
        "timezone": "WIB",
        "trading_hours": {
            "start": "09:00",
            "end": "16:00",
            "timezone": "WIB (UTC+7)"
        },
        "current_time": now.isoformat(),
        "market_day": "OPEN" if is_trading else "CLOSED" if is_trading_day else "WEEKEND",
        "next_open": _get_next_market_open(now, jakarta_tz).isoformat() if not is_trading else None,
    }


async def get_available_symbols() -> List[str]:
    """Get list of available IDX symbols."""
    return list(IDX_SYMBOLS.keys())


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

    if upper.endswith('.JK'):
        return 'IDR', 0

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

    # Align bars to Jakarta market sessions for consistent chart rendering.
    agg_df.index = agg_df.index.tz_convert('Asia/Jakarta')

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


def _get_next_market_open(current_time: datetime, jakarta_tz) -> datetime:
    """Calculate next IDX market open time."""
    # If before 09:00, market opens today at 09:00
    if current_time.hour < 9:
        return current_time.replace(hour=9, minute=0, second=0, microsecond=0)
    
    # If after 16:00 or weekend, calculate next trading day
    next_time = current_time + timedelta(days=1)
    
    # Skip weekends
    while next_time.weekday() > 4:
        next_time += timedelta(days=1)
    
    return next_time.replace(hour=9, minute=0, second=0, microsecond=0)


async def verify_connectivity() -> bool:
    """Test connectivity to data source."""
    try:
        ticker = yf.Ticker('BBCA.JK')
        info = ticker.info
        return bool(info)
    except Exception as e:
        logger.error(f"Failed to verify connectivity: {e}")
        return False
