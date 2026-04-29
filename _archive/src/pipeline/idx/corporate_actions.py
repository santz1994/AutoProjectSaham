"""Corporate action helpers for historical OHLCV ETL pipelines.

This module provides backward adjustment utilities so historical prices and
volumes stay comparable across split/dividend/rights events.
"""

from __future__ import annotations

import json
import os
from datetime import date, datetime
from typing import Any, Dict, Iterable, List, Mapping, Optional

try:
    import pandas as pd  # type: ignore[import-untyped]
except ImportError:
    pd = None


_PRICE_COLUMN_CANDIDATES = {
    "open": ["Open", "open", "OPEN"],
    "high": ["High", "high", "HIGH"],
    "low": ["Low", "low", "LOW"],
    "close": ["Close", "close", "CLOSE"],
}

_VOLUME_COLUMN_CANDIDATES = ["Volume", "volume", "VOLUME"]
_DATE_COLUMN_CANDIDATES = ["Date", "date", "Datetime", "datetime", "timestamp"]


def _normalize_symbol(symbol: Any) -> str:
    if symbol is None:
        return ""
    normalized = str(symbol).strip().upper()
    if normalized.endswith(".JK"):
        normalized = normalized[:-3]
    return normalized


def _as_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _as_normalized_date(value: Any):
    if pd is None:
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, date):
            return value
        if value is None:
            return None
        try:
            return datetime.fromisoformat(str(value)).date()
        except ValueError:
            return None

    ts = pd.to_datetime(value, errors="coerce")
    if pd.isna(ts):
        return None

    if hasattr(ts, "tzinfo") and ts.tzinfo is not None:
        ts = ts.tz_convert(None)

    return ts.normalize()


def index_actions_by_symbol(
    actions: Iterable[Mapping[str, Any]],
) -> Dict[str, List[Dict[str, Any]]]:
    """Build symbol-indexed action map from iterable action payloads."""
    indexed: Dict[str, List[Dict[str, Any]]] = {}

    for action in actions:
        if not isinstance(action, Mapping):
            continue
        symbol = _normalize_symbol(action.get("symbol") or action.get("ticker"))
        if not symbol:
            continue
        indexed.setdefault(symbol, []).append(dict(action))

    for symbol, symbol_actions in indexed.items():
        indexed[symbol] = sorted(
            symbol_actions,
            key=lambda item: _as_normalized_date(
                item.get("ex_date") or item.get("date") or item.get("effective_date")
            )
            or datetime.max.date(),
        )

    return indexed


def load_corporate_actions(
    path: Optional[str] = None,
) -> Dict[str, List[Dict[str, Any]]]:
    """Load corporate actions from JSON and index them by symbol.

    Accepted JSON formats:
    - list action payloads
    - object with `actions: []`
    - object mapping `SYMBOL -> [actions]`
    """
    env_path = os.getenv("AUTOSAHAM_CORPORATE_ACTIONS_FILE", "")
    raw_path = path if path is not None else env_path
    resolved_path = str(raw_path).strip()
    if not resolved_path:
        return {}

    if not os.path.exists(resolved_path):
        raise FileNotFoundError(f"Corporate action file not found: {resolved_path}")

    with open(resolved_path, "r", encoding="utf-8") as fh:
        payload = json.load(fh)

    raw_actions: List[Dict[str, Any]] = []

    if isinstance(payload, list):
        raw_actions = [dict(item) for item in payload if isinstance(item, Mapping)]
    elif isinstance(payload, Mapping):
        actions_list = payload.get("actions")
        if isinstance(actions_list, list):
            raw_actions = [
                dict(item)
                for item in actions_list
                if isinstance(item, Mapping)
            ]
        else:
            for symbol, items in payload.items():
                if not isinstance(items, list):
                    continue
                for item in items:
                    if not isinstance(item, Mapping):
                        continue
                    action = dict(item)
                    action.setdefault("symbol", symbol)
                    raw_actions.append(action)
    else:
        raise ValueError("Corporate action JSON must be a list or object")

    return index_actions_by_symbol(raw_actions)


def _resolve_ohlcv_columns(df):
    resolved: Dict[str, str] = {}
    for key, candidates in _PRICE_COLUMN_CANDIDATES.items():
        resolved_col = next(
            (candidate for candidate in candidates if candidate in df.columns),
            None,
        )
        if resolved_col is None:
            return None
        resolved[key] = resolved_col

    resolved["volume"] = next(
        (
            candidate
            for candidate in _VOLUME_COLUMN_CANDIDATES
            if candidate in df.columns
        ),
        "",
    )
    return resolved


def _resolve_date_series(df):
    if pd is None:
        return None

    if isinstance(df.index, pd.DatetimeIndex):
        dates = pd.Series(pd.to_datetime(df.index, errors="coerce"), index=df.index)
    else:
        date_col = next(
            (
                candidate
                for candidate in _DATE_COLUMN_CANDIDATES
                if candidate in df.columns
            ),
            None,
        )
        if date_col is None:
            return None
        dates = pd.to_datetime(df[date_col], errors="coerce")

    if hasattr(dates, "dt") and dates.dt.tz is not None:
        dates = dates.dt.tz_convert(None)
    return dates


def _multiply_columns(df, mask, columns: List[str], factor: float) -> None:
    for col in columns:
        numeric_values = pd.to_numeric(df.loc[mask, col], errors="coerce")
        df.loc[mask, col] = numeric_values * float(factor)


def apply_corporate_actions_to_ohlcv(frame, actions: Iterable[Mapping[str, Any]]):
    """Apply backward-adjustment corporate actions to an OHLCV DataFrame."""
    if pd is None or not isinstance(frame, pd.DataFrame):
        return frame

    if frame.empty:
        return frame.copy()

    columns = _resolve_ohlcv_columns(frame)
    if columns is None:
        return frame.copy()

    dates = _resolve_date_series(frame)
    if dates is None:
        return frame.copy()

    valid_date_mask = dates.notna()
    if not bool(valid_date_mask.any()):
        return frame.copy()

    work = frame.copy()
    ohlc_cols = [
        columns["open"],
        columns["high"],
        columns["low"],
        columns["close"],
    ]
    volume_col = columns.get("volume") or ""

    sorted_idx = dates.loc[valid_date_mask].sort_values(kind="mergesort").index
    ordered_dates = dates.loc[sorted_idx]
    ordered = work.loc[sorted_idx].copy()

    parsed_actions = []
    for action in actions:
        if not isinstance(action, Mapping):
            continue
        ex_date = _as_normalized_date(action.get("ex_date") or action.get("date"))
        if ex_date is None:
            continue
        parsed_actions.append((ex_date, dict(action)))

    parsed_actions.sort(key=lambda item: item[0])

    for ex_date, action in parsed_actions:
        pre_mask = ordered_dates < ex_date
        if not bool(pre_mask.any()):
            continue

        action_type = str(
            action.get("action_type") or action.get("type") or ""
        ).strip().lower()
        ratio = _as_float(action.get("ratio"))
        value = _as_float(action.get("value"))

        if action_type in {"split", "reverse_split", "bonus"}:
            if ratio is None:
                ratio = value
            if ratio is None or ratio <= 0:
                continue

            _multiply_columns(ordered, pre_mask, ohlc_cols, 1.0 / float(ratio))
            if volume_col:
                _multiply_columns(ordered, pre_mask, [volume_col], float(ratio))
            continue

        if action_type == "dividend":
            if value is None or value <= 0:
                continue

            ref_close = pd.to_numeric(
                ordered.loc[pre_mask, columns["close"]],
                errors="coerce",
            ).dropna()
            if ref_close.empty:
                continue

            latest_close = float(ref_close.iloc[-1])
            if latest_close <= 0 or latest_close <= float(value):
                continue

            price_factor = max((latest_close - float(value)) / latest_close, 0.01)
            _multiply_columns(ordered, pre_mask, ohlc_cols, price_factor)
            continue

        if action_type == "rights_issue":
            if ratio is None or ratio <= 0 or value is None or value < 0:
                continue

            ref_close = pd.to_numeric(
                ordered.loc[pre_mask, columns["close"]],
                errors="coerce",
            ).dropna()
            if ref_close.empty:
                continue

            latest_close = float(ref_close.iloc[-1])
            if latest_close <= 0:
                continue

            terp = (latest_close + float(ratio) * float(value)) / (1.0 + float(ratio))
            if terp <= 0:
                continue

            price_factor = max(terp / latest_close, 0.01)
            _multiply_columns(ordered, pre_mask, ohlc_cols, price_factor)
            if volume_col:
                _multiply_columns(ordered, pre_mask, [volume_col], 1.0 + float(ratio))

    result = frame.copy()
    result.loc[ordered.index, ordered.columns] = ordered

    if volume_col and volume_col in result.columns:
        try:
            volume_values = pd.to_numeric(result[volume_col], errors="coerce")
            if bool(volume_values.notna().all()):
                result[volume_col] = volume_values.round().astype(int)
        except (TypeError, ValueError):
            pass

    return result


def apply_corporate_actions_by_symbol(
    stocks: Mapping[str, Any],
    actions_by_symbol: Mapping[str, List[Dict[str, Any]]],
) -> Dict[str, Any]:
    """Apply corporate action adjustment for each stock frame by symbol key."""
    adjusted: Dict[str, Any] = {}

    for symbol, payload in dict(stocks).items():
        symbol_key = _normalize_symbol(symbol)
        symbol_actions = actions_by_symbol.get(symbol_key, [])
        if not symbol_actions:
            adjusted[symbol] = payload
            continue

        try:
            adjusted[symbol] = apply_corporate_actions_to_ohlcv(payload, symbol_actions)
        except (TypeError, ValueError, AttributeError, KeyError):
            adjusted[symbol] = payload

    return adjusted
