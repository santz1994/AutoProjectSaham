"""Background service that ingests market data via an adapter, persists
ticks and forwards normalized events into the application's event queue.
"""
from __future__ import annotations

import threading
import time
from typing import Optional


class MarketDataService:
    def __init__(self, adapter, db_path: str = "data/ticks.db"):
        self.adapter = adapter
        self.db_path = db_path
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        try:
            self.adapter.connect()
        except Exception:
            pass
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self):
        from src.api.event_queue import push_event
        from src.data.persistence import ensure_db, insert_tick

        ensure_db(self.db_path)
        try:
            for msg in self.adapter.listen():
                if self._stop.is_set():
                    break
                try:
                    if not isinstance(msg, dict):
                        continue
                    typ = msg.get("type")
                    if typ == "tick":
                        # persist and forward minimal tick event
                        insert_tick(
                            self.db_path,
                            msg.get("symbol", ""),
                            int(msg.get("ts", int(time.time()))),
                            float(msg.get("price", 0.0)),
                            int(msg.get("size", 0) or 0),
                            str(msg.get("side", "")),
                            msg.get("raw", {}),
                        )
                        push_event({"type": "tick", "symbol": msg.get("symbol"), "ts": msg.get("ts"), "price": msg.get("price")})
                    else:
                        # forward other messages directly
                        push_event(msg)
                except Exception:
                    # swallow per-message errors to keep the loop alive
                    try:
                        push_event({"type": "market_error", "error": "message_processing_failed"})
                    except Exception:
                        pass
                if self._stop.is_set():
                    break
        finally:
            try:
                self.adapter.disconnect()
            except Exception:
                pass

    def stop(self) -> None:
        self._stop.set()
        try:
            self.adapter.disconnect()
        except Exception:
            pass
        if self._thread:
            self._thread.join(timeout=2)
