"""Lightweight scheduler to run `AutonomousPipeline` periodically.

This scheduler is intentionally small and dependency-free so it can be
used in simple deployments or tests. For production use, consider
integrating APScheduler or a system-level scheduler.
"""
from __future__ import annotations

import logging
import threading
from typing import List, Optional

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
