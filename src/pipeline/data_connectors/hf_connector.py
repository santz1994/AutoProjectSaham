"""High-frequency OHLCV connector using CCXT.

This connector is designed for Phase 2 data foundation work:
- Pull up to 100,000+ candles (e.g., 5m)
- Return a clean pandas DataFrame
- Enforce strict interval and completeness checks when needed
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional, Sequence

import pandas as pd  # type: ignore[import-untyped]

from .schemas import validate_ohlcv_rows

logger = logging.getLogger(__name__)


def _import_ccxt() -> Any:
    try:
        import ccxt  # type: ignore
    except ImportError as exc:
        raise RuntimeError(
            "ccxt is required for hf_connector. Install with `pip install ccxt`."
        ) from exc
    return ccxt


def _build_exchange(
    exchange_id: str,
    market_type: str = "spot",
    exchange_config: Optional[Dict[str, Any]] = None,
) -> Any:
    ccxt = _import_ccxt()
    normalized_exchange = str(exchange_id or "").strip().lower()
    if not normalized_exchange:
        raise ValueError("exchange_id is required")

    if not hasattr(ccxt, normalized_exchange):
        raise ValueError(f"Unsupported exchange_id: {normalized_exchange}")

    exchange_cls = getattr(ccxt, normalized_exchange)
    cfg: Dict[str, Any] = {"enableRateLimit": True}
    if isinstance(exchange_config, dict):
        cfg.update(exchange_config)

    exchange = exchange_cls(cfg)

    # Best effort to align ccxt market type semantics across exchanges.
    if (
        market_type
        and hasattr(exchange, "options")
        and isinstance(exchange.options, dict)
    ):
        exchange.options = {**exchange.options, "defaultType": str(market_type)}

    exchange.load_markets()
    return exchange


def _fetch_ohlcv_with_retry(
    exchange: Any,
    symbol: str,
    timeframe: str,
    since_ms: int,
    limit: int,
    max_retries: int,
    retry_backoff_seconds: float,
) -> List[List[float]]:
    ccxt = _import_ccxt()
    retries = max(1, int(max_retries))
    delay = max(0.0, float(retry_backoff_seconds))

    for attempt in range(1, retries + 1):
        try:
            return exchange.fetch_ohlcv(
                symbol=symbol,
                timeframe=timeframe,
                since=int(since_ms),
                limit=int(limit),
            )
        except (
            ccxt.BaseError,
            RuntimeError,
            TimeoutError,
            ConnectionError,
            ValueError,
            TypeError,
        ) as exc:
            if attempt >= retries:
                raise RuntimeError(
                    f"Failed to fetch OHLCV after {retries} attempts: {exc}"
                ) from exc
            logger.warning(
                "fetch_ohlcv attempt %d/%d failed for %s %s: %s",
                attempt,
                retries,
                symbol,
                timeframe,
                exc,
            )
            if delay > 0:
                time.sleep(delay)

    return []


def _normalize_ohlcv_rows(raw_rows: Sequence[Sequence[Any]]) -> List[List[float]]:
    by_timestamp: Dict[int, List[float]] = {}
    for row in raw_rows:
        if not isinstance(row, (list, tuple)) or len(row) < 6:
            continue

        try:
            ts = int(row[0])
            normalized = [
                ts,
                float(row[1]),
                float(row[2]),
                float(row[3]),
                float(row[4]),
                float(row[5]),
            ]
        except (TypeError, ValueError):
            continue

        by_timestamp[ts] = normalized

    return [by_timestamp[k] for k in sorted(by_timestamp.keys())]


def _assert_regular_interval(
    rows: Sequence[Sequence[float]],
    interval_ms: int,
    strict: bool,
) -> None:
    if len(rows) <= 1:
        return

    gaps = 0
    for i in range(1, len(rows)):
        diff = int(rows[i][0]) - int(rows[i - 1][0])
        if diff != interval_ms:
            gaps += 1

    if gaps and strict:
        raise RuntimeError(
            "Detected "
            f"{gaps} interval gap(s). Expected fixed interval: {interval_ms} ms."
        )


def fetch_historical_data_with_exchange(
    exchange: Any,
    symbol: str,
    timeframe: str = "5m",
    candles: int = 100_000,
    batch_limit: int = 1_000,
    since_ms: Optional[int] = None,
    strict: bool = True,
    max_retries: int = 5,
    retry_backoff_seconds: float = 1.5,
    sleep_seconds: Optional[float] = None,
) -> pd.DataFrame:
    """Fetch historical OHLCV data and return a clean pandas DataFrame.

    Parameters:
    - exchange: Instantiated ccxt exchange client
    - symbol: Trading pair symbol (e.g., BTC/USDT)
    - timeframe: CCXT timeframe string (default: 5m)
    - candles: Total candles requested (default: 100,000)
    - batch_limit: Per-request limit, usually <= 1000 depending on exchange
    - since_ms: Start timestamp in milliseconds. If None, back-calculated.
    - strict: If True, raises when completeness/interval checks fail
    - max_retries: Per-request retry attempts
    - retry_backoff_seconds: Sleep between retries
    - sleep_seconds: Inter-request sleep. If None, uses exchange.rateLimit
    """
    total_candles = int(candles)
    if total_candles <= 0:
        raise ValueError("candles must be > 0")

    safe_batch_limit = max(10, int(batch_limit))
    safe_batch_limit = min(safe_batch_limit, total_candles)

    if not hasattr(exchange, "parse_timeframe"):
        raise ValueError("exchange is missing parse_timeframe")

    timeframe_seconds = int(exchange.parse_timeframe(timeframe))
    if timeframe_seconds <= 0:
        raise ValueError(f"Invalid timeframe: {timeframe}")
    interval_ms = timeframe_seconds * 1000

    now_ms = (
        int(exchange.milliseconds())
        if hasattr(exchange, "milliseconds")
        else int(time.time() * 1000)
    )
    start_ms = (
        int(since_ms)
        if since_ms is not None
        else now_ms - (interval_ms * total_candles)
    )

    inter_request_sleep = (
        max(0.0, float(sleep_seconds))
        if sleep_seconds is not None
        else max(0.0, float(getattr(exchange, "rateLimit", 0)) / 1000.0)
    )

    cursor = start_ms
    collected: List[List[Any]] = []

    while len(collected) < total_candles:
        remaining = total_candles - len(collected)
        request_limit = min(safe_batch_limit, remaining)

        chunk = _fetch_ohlcv_with_retry(
            exchange=exchange,
            symbol=symbol,
            timeframe=timeframe,
            since_ms=cursor,
            limit=request_limit,
            max_retries=max_retries,
            retry_backoff_seconds=retry_backoff_seconds,
        )

        if not chunk:
            break

        collected.extend(chunk)

        last_ts = int(chunk[-1][0])
        next_cursor = last_ts + interval_ms
        if next_cursor <= cursor:
            next_cursor = cursor + interval_ms
        cursor = next_cursor

        if len(chunk) < request_limit:
            break

        if inter_request_sleep > 0:
            time.sleep(inter_request_sleep)

    normalized = _normalize_ohlcv_rows(collected)
    if len(normalized) > total_candles:
        normalized = normalized[-total_candles:]

    if strict and len(normalized) < total_candles:
        raise RuntimeError(
            "Incomplete dataset. "
            f"Requested {total_candles} candles, got {len(normalized)}."
        )

    _assert_regular_interval(normalized, interval_ms, strict=strict)

    if not normalized:
        return pd.DataFrame(
            columns=[
                "timestamp",
                "datetime",
                "open",
                "high",
                "low",
                "close",
                "volume",
            ]
        )

    df = pd.DataFrame(
        normalized,
        columns=["timestamp", "open", "high", "low", "close", "volume"],
    )
    df["datetime"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
    df = df[["timestamp", "datetime", "open", "high", "low", "close", "volume"]]
    df = df.sort_values("timestamp").drop_duplicates(subset=["timestamp"], keep="last")
    df = df.set_index("datetime", drop=False)

    # Connector-level schema guard to ensure OHLCV consistency before persistence.
    validate_ohlcv_rows(df[["open", "high", "low", "close"]].to_dict("records"))

    return df


def fetch_historical_data(
    exchange_id: str = "binance",
    symbol: str = "BTC/USDT",
    timeframe: str = "5m",
    candles: int = 100_000,
    batch_limit: int = 1_000,
    since_ms: Optional[int] = None,
    market_type: str = "spot",
    strict: bool = True,
    max_retries: int = 5,
    retry_backoff_seconds: float = 1.5,
    sleep_seconds: Optional[float] = None,
    exchange_config: Optional[Dict[str, Any]] = None,
) -> pd.DataFrame:
    """Build an exchange client with CCXT and fetch historical OHLCV data."""
    exchange = _build_exchange(
        exchange_id=exchange_id,
        market_type=market_type,
        exchange_config=exchange_config,
    )
    return fetch_historical_data_with_exchange(
        exchange=exchange,
        symbol=symbol,
        timeframe=timeframe,
        candles=candles,
        batch_limit=batch_limit,
        since_ms=since_ms,
        strict=strict,
        max_retries=max_retries,
        retry_backoff_seconds=retry_backoff_seconds,
        sleep_seconds=sleep_seconds,
    )
