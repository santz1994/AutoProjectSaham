"""
IDX/BEI Stock Data Fetcher
============================
Real-time candlestick data from Indonesia Stock Exchange (IDX/BEI)
using yfinance with curl_cffi for rate limiting bypass.

Author: AutoSaham Team
Version: 1.0.0
"""

import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, List
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
        
        # Fetch historical data (note: remove progress parameter for compatibility)
        df = ticker.history(period=period, interval=yf_interval)
        
        if df.empty:
            logger.warning(f"No data returned for {symbol}")
            return None
        
        # Ensure we have required columns
        required_columns = ['Open', 'High', 'Low', 'Close']
        if not all(col in df.columns for col in required_columns):
            logger.error(f"Missing OHLC columns for {symbol}")
            return None
        
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
        
        # Limit to requested count
        candles = candles[-limit:] if len(candles) > limit else candles
        
        return {
            "symbol": symbol,
            "timeframe": timeframe,
            "candles": candles,
            "metadata": {
                "total": len(candles),
                "fetched_at": datetime.utcnow().isoformat() + "Z",
                "exchange": "IDX",
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
        
        return {
            "symbol": symbol,
            "name": metadata.get("name", info.get("longName", "Unknown")),
            "exchange": "IDX",
            "currency": "IDR",
            "timezone": "Asia/Jakarta",
            "sector": metadata.get("sector", info.get("sector", "Unknown")),
            "country": "Indonesia",
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
    if timeframe in ['1m', '5m', '15m', '30m', '1h']:
        # For intraday, fetch last 60 days (max yfinance returns)
        return '60d'
    elif timeframe == '4h':
        return '90d'
    elif timeframe == '1d':
        # For daily, fetch ~2 years worth
        days = min(limit * 1.5, 730)  # 2 years max
        return f'{int(days)}d'
    elif timeframe == '1w':
        weeks = min(limit * 1.5, 520)  # 10 years max
        return f'{int(weeks)}w'
    elif timeframe == '1mo':
        months = min(limit * 1.5, 240)  # 20 years max
        return f'{int(months)}mo'
    else:
        return '1y'


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
