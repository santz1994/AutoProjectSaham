"""Market data adapter abstractions and a simple Alpaca adapter fallback.

This module provides a minimal `MarketDataAdapter` ABC and a pragmatic
`AlpacaMarketDataAdapter` that uses a simulated generator when Alpaca
libraries are not available. The adapter yields normalized "tick" events
that can be persisted and forwarded via the event queue.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Dict, Iterable, List
import asyncio
import logging
import queue
import time
import random
import threading

from src.data.idx_api_client import BEIWebSocketClient, Tick


logger = logging.getLogger(__name__)


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


class IDXMarketDataAdapter(MarketDataAdapter):
    """Streaming-native IDX adapter backed by BEI websocket client.

    The internal BEI client is async while `MarketDataService` expects a
    synchronous iterator. This adapter bridges both via a thread-safe queue.
    """

    def __init__(
        self,
        symbols: List[str] | None = None,
        username: str | None = None,
        password: str | None = None,
        queue_size: int = 5000,
    ):
        super().__init__(symbols=symbols)
        self.username = str(username or "").strip()
        self.password = str(password or "").strip()
        self.queue_size = int(max(500, queue_size))

        self._running = False
        self._event_queue: queue.Queue = queue.Queue(maxsize=self.queue_size)
        self._worker: threading.Thread | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._client: BEIWebSocketClient | None = None

    def configured(self) -> bool:
        return bool(self.username and self.password)

    def connect(self) -> bool:
        if not self.configured():
            logger.warning(
                "IDX websocket credentials missing; stream adapter not started"
            )
            return False

        if self._running:
            return True

        self._running = True
        self._worker = threading.Thread(target=self._run_worker, daemon=True)
        self._worker.start()
        return True

    def subscribe(self, symbols: List[str]) -> None:
        self.symbols = [str(item or "").strip() for item in symbols if str(item or "").strip()]

    def _run_worker(self) -> None:
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_until_complete(self._stream_loop())
        except Exception as exc:
            logger.error("IDX stream worker failed: %s", exc)
        finally:
            try:
                if self._loop is not None and not self._loop.is_closed():
                    self._loop.close()
            except Exception:
                pass

    async def _stream_loop(self) -> None:
        self._client = BEIWebSocketClient(self.username, self.password)

        connected = False
        try:
            connected = await self._client.connect()
        except Exception as exc:
            logger.error("IDX websocket connect failed: %s", exc)

        if not connected:
            self._running = False
            return

        symbols = self.symbols or ["BBCA"]

        def _on_tick(tick: Tick) -> None:
            payload = {
                "type": "tick",
                "symbol": tick.symbol,
                "ts": int(tick.timestamp.timestamp()),
                "price": float(tick.price),
                "size": int(tick.quantity),
                "side": str(tick.side or ""),
                "raw": {
                    "trade_id": tick.trade_id,
                    "buyer": tick.buyer,
                    "seller": tick.seller,
                },
            }
            try:
                self._event_queue.put_nowait(payload)
            except queue.Full:
                try:
                    _ = self._event_queue.get_nowait()
                except queue.Empty:
                    pass
                try:
                    self._event_queue.put_nowait(payload)
                except queue.Full:
                    pass

        try:
            await self._client.stream_ticks(symbols, _on_tick)
        except Exception as exc:
            logger.error("IDX websocket stream failed: %s", exc)
        finally:
            try:
                await self._client.disconnect()
            except Exception:
                pass
            self._running = False

    def listen(self):
        while self._running or not self._event_queue.empty():
            try:
                message = self._event_queue.get(timeout=0.25)
                yield message
            except queue.Empty:
                continue

    def disconnect(self) -> None:
        self._running = False

        loop = self._loop
        client = self._client
        if loop and client and not loop.is_closed():
            try:
                future = asyncio.run_coroutine_threadsafe(client.disconnect(), loop)
                future.result(timeout=2)
            except Exception:
                pass

        if self._worker and self._worker.is_alive():
            self._worker.join(timeout=2)


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
