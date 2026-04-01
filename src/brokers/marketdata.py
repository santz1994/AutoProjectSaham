"""Market data adapter abstractions and a simple Alpaca adapter fallback.

This module provides a minimal `MarketDataAdapter` ABC and a pragmatic
`AlpacaMarketDataAdapter` that uses a simulated generator when Alpaca
libraries are not available. The adapter yields normalized "tick" events
that can be persisted and forwarded via the event queue.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Dict, Iterable, List
import time
import random


class MarketDataAdapter(ABC):
    def __init__(self, symbols: List[str] | None = None):
        self.symbols = [s for s in (symbols or [])]

    @abstractmethod
    def connect(self) -> bool:
        raise NotImplementedError()

    @abstractmethod
    def subscribe(self, symbols: List[str]) -> None:
        raise NotImplementedError()

    @abstractmethod
    def listen(self) -> Iterable[Dict]:
        """Yield normalized market messages (dict)."""

    @abstractmethod
    def disconnect(self) -> None:
        raise NotImplementedError()


class AlpacaMarketDataAdapter(MarketDataAdapter):
    """Adapter that prefers a real Alpaca connection but falls back to a
    local synthetic tick generator when the Alpaca SDK is unavailable.

    The real implementation is intentionally lightweight here: if the
    production `alpaca` websockets client is available the adapter should
    be extended to use it. For now we provide a stable simulation so the
    rest of the system can be exercised without credentials.
    """

    def __init__(self, symbols: List[str] | None = None, interval: float = 0.5):
        super().__init__(symbols=symbols)
        self._running = False
        self._interval = float(interval)
        # detect presence of official client libraries lazily
        try:
            import alpaca_trade_api as _alpaca  # type: ignore

            self._has_alpaca = True
        except Exception:
            self._has_alpaca = False

    def connect(self) -> bool:
        self._running = True
        return True

    def subscribe(self, symbols: List[str]) -> None:
        self.symbols = [s for s in symbols]

    def listen(self):
        """Yield simulated tick messages until `disconnect()` is called.

        Message format (normalized):
        {
            "type": "tick",
            "symbol": "AAPL",
            "ts": 1670000000,
            "price": 123.45,
            "size": 100,
            "side": "buy",
            "raw": {...}
        }
        """
        # simple random-walk generator for each symbol
        last = {s: 100.0 + random.random() * 10 for s in (self.symbols or ["IDX"])}
        while self._running:
            for s, base in list(last.items()):
                # small random move
                delta = (random.random() - 0.5) * 0.5
                price = max(0.01, base + delta)
                last[s] = price
                msg = {
                    "type": "tick",
                    "symbol": s,
                    "ts": int(time.time()),
                    "price": float(round(price, 6)),
                    "size": int(max(1, random.gauss(20, 10))),
                    "side": "buy" if random.random() > 0.5 else "sell",
                    "raw": {},
                }
                yield msg
                time.sleep(self._interval)

    def disconnect(self) -> None:
        self._running = False
