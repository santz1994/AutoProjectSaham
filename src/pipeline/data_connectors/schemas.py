"""Schema and validation helpers for market data connectors.

Provides a lightweight Pydantic-backed validator when available, with a
fallback pure-Python validation to ensure connectors emit sane OHLC/price
series before they are persisted to the feature store.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

try:
    from pydantic import BaseModel
    # detect v2-style model validators when available
    try:
        from pydantic import model_validator  # type: ignore
        PYDANTIC_V2 = True
    except Exception:
        PYDANTIC_V2 = False

    try:
        from pydantic import root_validator  # type: ignore
        PYDANTIC_V1 = True
    except Exception:
        PYDANTIC_V1 = False

    PYDANTIC_AVAILABLE = True

    if PYDANTIC_V2:
        # Pydantic v2: use @model_validator
        from pydantic import model_validator

        class _PriceSeries(BaseModel):
            prices: List[float]

            @model_validator(mode='after')
            def non_empty_and_numeric(self):
                v = getattr(self, 'prices', None)
                if not isinstance(v, list) or len(v) == 0:
                    raise ValueError('prices must be a non-empty list')
                for x in v:
                    if not isinstance(x, (int, float)):
                        raise ValueError('all prices must be numeric')
                    if x is None or (isinstance(x, float) and (x != x)):
                        raise ValueError('price must be a finite number')
                    if float(x) <= 0.0:
                        raise ValueError('price must be positive')
                return self


        class OHLCVRow(BaseModel):
            date: Optional[str] = None
            open: float
            high: float
            low: float
            close: float
            adj_close: Optional[float] = None
            volume: Optional[int] = None

            @model_validator(mode='after')
            def check_values(self):
                o = float(getattr(self, 'open'))
                h = float(getattr(self, 'high'))
                l = float(getattr(self, 'low'))
                c = float(getattr(self, 'close'))
                v = getattr(self, 'volume', None)

                for x in (o, h, l, c):
                    if x != x:
                        raise ValueError('OHLC values must be finite numbers')
                    if x <= 0.0:
                        raise ValueError('OHLC values must be > 0')

                if h < l:
                    raise ValueError('high must be >= low')
                if not (l <= o <= h):
                    raise ValueError('open must be between low and high')
                if not (l <= c <= h):
                    raise ValueError('close must be between low and high')

                if v is not None:
                    try:
                        iv = int(v)
                    except Exception:
                        raise ValueError('volume must be an integer')
                    if iv < 0:
                        raise ValueError('volume must be >= 0')
                    object.__setattr__(self, 'volume', iv)

                if getattr(self, 'adj_close', None) is not None:
                    try:
                        object.__setattr__(self, 'adj_close', float(getattr(self, 'adj_close')))
                    except Exception:
                        raise ValueError('adj_close must be numeric')

                return self

    elif PYDANTIC_V1:
        # Pydantic v1: use @root_validator
        from pydantic import root_validator

        class _PriceSeries(BaseModel):
            prices: List[float]

            @root_validator
            def non_empty_and_numeric(cls, values):
                v = values.get('prices')
                if not isinstance(v, list) or len(v) == 0:
                    raise ValueError('prices must be a non-empty list')
                for x in v:
                    if not isinstance(x, (int, float)):
                        raise ValueError('all prices must be numeric')
                    if x is None or (isinstance(x, float) and (x != x)):
                        raise ValueError('price must be a finite number')
                    if float(x) <= 0.0:
                        raise ValueError('price must be positive')
                return values


        class OHLCVRow(BaseModel):
            date: Optional[str] = None
            open: float
            high: float
            low: float
            close: float
            adj_close: Optional[float] = None
            volume: Optional[int] = None

            @root_validator
            def check_values(cls, values):
                o = float(values.get('open'))
                h = float(values.get('high'))
                l = float(values.get('low'))
                c = float(values.get('close'))
                v = values.get('volume')

                for x in (o, h, l, c):
                    if x != x:
                        raise ValueError('OHLC values must be finite numbers')
                    if x <= 0.0:
                        raise ValueError('OHLC values must be > 0')

                if h < l:
                    raise ValueError('high must be >= low')
                if not (l <= o <= h):
                    raise ValueError('open must be between low and high')
                if not (l <= c <= h):
                    raise ValueError('close must be between low and high')

                if v is not None:
                    try:
                        iv = int(v)
                    except Exception:
                        raise ValueError('volume must be an integer')
                    if iv < 0:
                        raise ValueError('volume must be >= 0')
                    values['volume'] = iv

                if values.get('adj_close') is not None:
                    try:
                        values['adj_close'] = float(values.get('adj_close'))
                    except Exception:
                        raise ValueError('adj_close must be numeric')

                return values

    else:
        PYDANTIC_AVAILABLE = False

except Exception:
    PYDANTIC_AVAILABLE = False


def validate_price_series(prices: List[float]) -> bool:
    """Validate a list of prices. Returns True when valid, raises ValueError otherwise.

    Uses Pydantic when available for stricter validation; falls back to a
    lightweight check otherwise.
    """
    if PYDANTIC_AVAILABLE:
        _PriceSeries(prices=prices)
        return True

    # fallback checks
    if not isinstance(prices, (list, tuple)):
        raise ValueError('prices must be a list or tuple')
    if len(prices) == 0:
        raise ValueError('prices must be non-empty')
    for p in prices:
        if not isinstance(p, (int, float)):
            raise ValueError('all prices must be numeric')
        if p is None:
            raise ValueError('price must not be None')
        try:
            pv = float(p)
        except Exception:
            raise ValueError('price value not castable to float')
        if pv != pv:  # NaN
            raise ValueError('price must be finite number')
        if pv <= 0.0:
            raise ValueError('price must be > 0')
    return True


def _normalize_row_for_ohlcv(row: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize a mapping-like row to canonical OHLCV keys.

    Accepts a dict where keys may be 'Open', 'open', 'Adj Close', '5. adjusted close',
    'Volume', etc. Returns a dict with keys: date, open, high, low, close, adj_close, volume.
    """
    if not isinstance(row, dict):
        # try to coerce map-like objects
        try:
            row = dict(row)
        except Exception:
            raise ValueError('row must be a mapping-like object')

    lower = {str(k).lower().strip(): v for k, v in row.items()}

    def _fetch(candidates: List[str]):
        for c in candidates:
            if c in lower:
                return lower[c]
        # substring match fallback
        for k, v in lower.items():
            for c in candidates:
                if c in k:
                    return v
        return None

    return {
        'date': _fetch(['date', 'time', 'timestamp', 'index']),
        'open': _fetch(['open', 'o']),
        'high': _fetch(['high', 'h']),
        'low': _fetch(['low', 'l']),
        'close': _fetch(['close', 'c']),
        'adj_close': _fetch(['adj close', 'adj_close', 'adjusted close', '5. adjusted close']),
        'volume': _fetch(['volume', 'vol', 'v']),
    }


def validate_ohlcv_rows(rows: List[Dict[str, Any]]) -> bool:
    """Validate an iterable of OHLCV-like rows.

    Each row may be a dict-like mapping (as returned by `df.reset_index().to_dict('records')`).
    Raises ValueError on validation failure; returns True when valid.
    """
    if not isinstance(rows, (list, tuple)):
        raise ValueError('rows must be a list or tuple of mapping-like rows')

    if PYDANTIC_AVAILABLE:
        for r in rows:
            norm = _normalize_row_for_ohlcv(r)
            # Pydantic model will raise on invalid input
            OHLCVRow(**norm)
        return True

    # fallback checks
    if len(rows) == 0:
        raise ValueError('rows must be non-empty')

    for idx, r in enumerate(rows):
        norm = _normalize_row_for_ohlcv(r)
        try:
            o = norm.get('open')
            h = norm.get('high')
            l = norm.get('low')
            c = norm.get('close')
        except Exception:
            raise ValueError(f'row {idx} missing OHLC columns')

        if o is None or h is None or l is None or c is None:
            raise ValueError(f'row {idx} missing OHLC values')

        try:
            o = float(o)
            h = float(h)
            l = float(l)
            c = float(c)
        except Exception:
            raise ValueError(f'row {idx} OHLC values not numeric')

        if any(x != x for x in (o, h, l, c)):
            raise ValueError(f'row {idx} contains non-finite OHLC values')
        if any(x <= 0.0 for x in (o, h, l, c)):
            raise ValueError(f'row {idx} OHLC values must be > 0')
        if h < l:
            raise ValueError(f'row {idx} high < low')
        if not (l <= o <= h):
            raise ValueError(f'row {idx} open not between low/high')
        if not (l <= c <= h):
            raise ValueError(f'row {idx} close not between low/high')

        vol = norm.get('volume')
        if vol is not None:
            try:
                iv = int(vol)
            except Exception:
                raise ValueError(f'row {idx} volume not integer')
            if iv < 0:
                raise ValueError(f'row {idx} volume must be >= 0')

    return True
