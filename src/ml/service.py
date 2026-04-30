"""Lightweight ML trainer service that builds a dataset from persisted
ticks and invokes the existing `train_model` workflow.

This service is intentionally conservative: it depends on `pandas` for
data aggregation (if available) and falls back to no-op when data is
insufficient. Trained artifacts are written to `models/` and a
`model_trained` event is emitted via the event queue.
"""
from __future__ import annotations

import os
import threading
import time
from typing import Optional


class MLTrainerService:
    def __init__(self, schedule_seconds: int = 24 * 3600, db_path: str = "data/ticks.db", models_dir: str = "models"):
        self.schedule_seconds = int(schedule_seconds)
        self.db_path = db_path
        self.models_dir = models_dir
        os.makedirs(self.models_dir, exist_ok=True)
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                self.run_once()
            except Exception:
                try:
                    from src.api.event_queue import push_event

                    push_event({"type": "ml_error", "error": "trainer_run_failed"})
                except Exception:
                    pass
            # sleep with early exit
            for _ in range(max(1, int(self.schedule_seconds))):
                if self._stop.is_set():
                    break
                time.sleep(1)

    def run_once(self) -> None:
        """Build a small dataset from ticks and call `train_model`.

        The function is conservative: if `pandas` is not available or there
        is insufficient data it exits silently.
        """
        try:
            from src.data.persistence import query_ticks_to_df
        except Exception:
            return

        df = query_ticks_to_df(self.db_path)
        if df is None:
            # pandas not available
            return
        try:
            import pandas as pd

            if df.empty:
                return
            # convert ts to datetime and resample per-minute bars per symbol
            df["ts_dt"] = pd.to_datetime(df["ts"], unit="s")
            df = df.set_index("ts_dt")
            agg = df.groupby("symbol").resample("1min").agg({"price": ["first", "max", "min", "last"], "size": "sum"})
            # flatten columns
            agg.columns = ["open", "high", "low", "close", "volume"]
            agg = agg.reset_index()
            # compute next-period return and binary label
            agg = agg.sort_values(["symbol", "ts_dt"]).reset_index(drop=True)
            agg["future_close"] = agg.groupby("symbol")["close"].shift(-1)
            agg["future_return"] = (agg["future_close"] / agg["close"] - 1.0)
            agg["label"] = (agg["future_return"] > 0).astype(int)
            ds = agg.dropna(subset=["label"]).copy()
            if ds.empty:
                return
            csv_path = os.path.join("data", "dataset.csv")
            os.makedirs(os.path.dirname(csv_path) or ".", exist_ok=True)
            ds.to_csv(csv_path, index=False)
            # call existing trainer
            from src.ml.trainer import train_model

            model_out = os.path.join(self.models_dir, f"model_{int(time.time())}.joblib")
            res = train_model(csv_path, target_col="label", model_out=model_out, use_optuna=False)
            # notify via event queue that a model was trained
            try:
                from src.api.event_queue import push_event

                push_event({"type": "model_trained", "path": model_out, "meta": res})
            except Exception:
                pass
        except Exception:
            # emit a lightweight event for visibility
            try:
                from src.api.event_queue import push_event

                push_event({"type": "ml_error", "error": "dataset_build_failed"})
            except Exception:
                pass

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2)
