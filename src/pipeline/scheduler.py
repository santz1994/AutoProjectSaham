"""Lightweight scheduler to run `AutonomousPipeline` periodically.

This scheduler is intentionally small and dependency-free so it can be
used in simple deployments or tests. For production use, consider
integrating APScheduler or a system-level scheduler.

Fase 5 (MIMO Sentiment Integration):
- Added SentimentScheduler that polls MIMO-v2.5-Pro via OpenRouter API
  every configurable interval (default 4h / market close) and injects
  the resulting sentiment vector into the RL observation pipeline.
"""
from __future__ import annotations

import asyncio
import logging
import os
import threading
from typing import Any, Callable, Dict, List, Optional

from .runner import AutonomousPipeline


class PipelineScheduler:
    def __init__(
        self,
        pipeline: AutonomousPipeline,
        symbols: List[str],
        interval_seconds: float = 3600.0,
        run_on_start: bool = False,
        persist_db: Optional[str] = None,
        logger: Optional[logging.Logger] = None,
    ):
        self.pipeline = pipeline
        self.symbols = list(symbols)
        self.interval_seconds = float(interval_seconds)
        self.persist_db = persist_db
        self.logger = logger or logging.getLogger("autosaham.pipeline.scheduler")

        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._lock = threading.Lock()

        if run_on_start:
            # run once synchronously
            self.run_once()

    def _loop(self) -> None:
        while not self._stop_event.wait(self.interval_seconds):
            try:
                self.logger.info(
                    "Scheduler invoking pipeline.run for %d symbols", len(self.symbols)
                )
                self.pipeline.run(self.symbols, persist_db=self.persist_db)
            except Exception:
                self.logger.exception("scheduled run failed")

    def start(self) -> bool:
        """Start the background scheduler thread. Returns False if already running."""
        with self._lock:
            if self._thread and self._thread.is_alive():
                return False
            self._stop_event.clear()
            self._thread = threading.Thread(
                target=self._loop, name="PipelineScheduler", daemon=True
            )
            self._thread.start()
            return True

    def stop(self, timeout: Optional[float] = None) -> None:
        """Stop the scheduler and wait for the thread to exit (best-effort)."""
        with self._lock:
            self._stop_event.set()
            t = self._thread
            if t:
                t.join(timeout)
                self._thread = None

    def run_once(self) -> None:
        """Run the pipeline once synchronously."""
        try:
            self.logger.info("Manual run_once for %d symbols", len(self.symbols))
            self.pipeline.run(self.symbols, persist_db=self.persist_db)
        except Exception:
            self.logger.exception("run_once failed")


# ============================================================================
# MIMO Sentiment Scheduler
# ============================================================================

class SentimentScheduler:
    """Periodic scheduler that polls MIMO-v2.5-Pro for sentiment analysis.

    Runs in a background thread. Every ``interval_seconds`` (default 14400 = 4h),
    it:
      1. Fetches latest market news/context for each symbol
      2. Calls MIMO-v2.5-Pro async connector for sentiment analysis
      3. Stores the resulting sentiment vector for RL agent consumption

    The sentiment vector is stored in ``self.latest_sentiment`` and can be
    accessed by the RL agent before calling ``predict()``.

    Args:
        symbols: List of trading symbols (e.g. ["BTC/USDT", "ETH/USDT"])
        interval_seconds: How often to poll (default 14400 = 4 hours)
        news_callback: Optional callable that returns news text for a symbol.
            Signature: ``news_callback(symbol: str) -> str``
            If None, a stub returning empty string is used.
        on_sentiment: Optional callback invoked with
            ``on_sentiment(symbol: str, result: SentimentResult)``
            after each successful sentiment fetch.
        logger: Optional logger instance.
    """

    def __init__(
        self,
        symbols: List[str],
        interval_seconds: Optional[float] = None,
        news_callback: Optional[Callable[[str], str]] = None,
        on_sentiment: Optional[Callable[[str, Any], None]] = None,
        logger: Optional[logging.Logger] = None,
    ):
        self.symbols = list(symbols)
        self.interval_seconds = float(
            interval_seconds
            or os.getenv("MIMO_SENTIMENT_INTERVAL", "14400")
        )
        self.news_callback = news_callback or (lambda symbol: "")
        self.on_sentiment = on_sentiment
        self.logger = logger or logging.getLogger("autosaham.pipeline.sentiment_scheduler")

        # Latest sentiment vector per symbol: {symbol: SentimentResult}
        self.latest_sentiment: Dict[str, Any] = {}
        # Latest raw vector per symbol: {symbol: List[float]}
        self.latest_vectors: Dict[str, List[float]] = {}

        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._lock = threading.Lock()
        self._cycle_count: int = 0

    def _run_async(self, coro):
        """Run an async coroutine in a dedicated event loop (for thread usage)."""
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                return pool.submit(asyncio.run, coro).result(timeout=120)
        else:
            return asyncio.run(coro)

    def _fetch_sentiment_cycle(self) -> None:
        """Run one full sentiment fetch cycle for all symbols."""
        # Lazy import to avoid circular dependency at module load
        from .data_connectors.mimo_llm_connector import MimoLLMConnector

        async def _run():
            async with MimoLLMConnector() as connector:
                for symbol in self.symbols:
                    try:
                        # Get news context for this symbol
                        news_text = self.news_callback(symbol)
                        if not news_text:
                            # Use market overview as fallback context
                            news_text = (
                                f"Current market conditions for {symbol}. "
                                "Provide general sentiment analysis based on "
                                "recent crypto/forex market trends."
                            )

                        result = await connector.analyze_sentiment(news_text)

                        with self._lock:
                            self.latest_sentiment[symbol] = result
                            self.latest_vectors[symbol] = result.to_vector()

                        if self.on_sentiment:
                            try:
                                self.on_sentiment(symbol, result)
                            except Exception:
                                self.logger.warning("on_sentiment callback error for %s", symbol, exc_info=True)

                        self.logger.info(
                            "Sentiment %s: score=%.3f conf=%.3f risk=%s regime=%s",
                            symbol, result.sentiment_score, result.confidence,
                            result.risk_level, result.market_regime_hint,
                        )
                    except Exception:
                        self.logger.warning("Sentiment fetch failed for %s", symbol, exc_info=True)

        try:
            self._run_async(_run())
        except Exception:
            self.logger.exception("Sentiment cycle failed")

    def _loop(self) -> None:
        self.logger.info(
            "SentimentScheduler started: %d symbols, interval=%.0fs",
            len(self.symbols), self.interval_seconds,
        )
        # Run immediately on start
        self._cycle_count += 1
        self.logger.info("Sentiment cycle %d starting", self._cycle_count)
        self._fetch_sentiment_cycle()

        while not self._stop_event.wait(self.interval_seconds):
            self._cycle_count += 1
            self.logger.info("Sentiment cycle %d starting", self._cycle_count)
            self._fetch_sentiment_cycle()

    def start(self) -> bool:
        """Start the sentiment scheduler background thread."""
        with self._lock:
            if self._thread and self._thread.is_alive():
                return False
            self._stop_event.clear()
            self._thread = threading.Thread(
                target=self._loop, name="SentimentScheduler", daemon=True
            )
            self._thread.start()
            return True

    def stop(self, timeout: Optional[float] = None) -> None:
        """Stop the sentiment scheduler."""
        with self._lock:
            self._stop_event.set()
            t = self._thread
            if t:
                t.join(timeout)
                self._thread = None

    def get_latest_vector(self, symbol: str) -> List[float]:
        """Get the latest sentiment vector for a symbol (thread-safe).

        Returns 7-element float list. If no sentiment data is available yet,
        returns a neutral vector [0.0, 0.0, 0.5, 0.0, 0.0, 1.0, 0.0].
        """
        with self._lock:
            vec = self.latest_vectors.get(symbol)
            if vec is not None:
                return list(vec)
        # Neutral default: no sentiment, medium risk, ranging regime
        return [0.0, 0.0, 0.5, 0.0, 0.0, 1.0, 0.0]

    def get_all_vectors(self) -> Dict[str, List[float]]:
        """Get latest sentiment vectors for all symbols."""
        with self._lock:
            return {s: list(v) for s, v in self.latest_vectors.items()}

    def get_stats(self) -> Dict[str, Any]:
        """Get scheduler statistics."""
        with self._lock:
            return {
                "symbols": list(self.symbols),
                "interval_seconds": self.interval_seconds,
                "cycle_count": self._cycle_count,
                "latest_sentiment_count": len(self.latest_sentiment),
                "is_running": self._thread is not None and self._thread.is_alive(),
            }
