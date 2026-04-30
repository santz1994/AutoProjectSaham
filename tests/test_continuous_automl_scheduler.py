"""Tests for Continuous AutoML Scheduler (Phase 4.2).

Validates:
- Scheduler lifecycle (start/stop/stats)
- Optuna HPO integration
- Walk-forward validation logic
- Model promotion to registry
- Run-once synchronous mode
"""
from __future__ import annotations

import json
import os
import tempfile
import threading
from pathlib import Path
from unittest import TestCase, main
from unittest.mock import MagicMock, patch


class TestContinuousAutoMLSchedulerLifecycle(TestCase):
    """Test scheduler start/stop/stats lifecycle."""

    def _make_scheduler(self, **kwargs):
        from src.pipeline.continuous_automl_scheduler import ContinuousAutoMLScheduler

        defaults = dict(
            data_path="nonexistent.csv",
            interval_hours=168.0,
            optuna_trials=2,
            walk_forward_splits=2,
        )
        defaults.update(kwargs)
        return ContinuousAutoMLScheduler(**defaults)

    def test_initial_stats(self):
        sched = self._make_scheduler()
        stats = sched.get_stats()
        self.assertFalse(stats["is_running"])
        self.assertEqual(stats["cycle_count"], 0)
        self.assertIsNone(stats["last_run"])
        self.assertEqual(stats["promoted_models_count"], 0)
        self.assertEqual(stats["optuna_trials"], 2)
        self.assertEqual(stats["walk_forward_splits"], 2)

    def test_start_and_stop(self):
        sched = self._make_scheduler(interval_hours=100.0)
        started = sched.start()
        self.assertTrue(started)
        stats = sched.get_stats()
        self.assertTrue(stats["is_running"])

        # Second start should return False (already running)
        second = sched.start()
        self.assertFalse(second)

        sched.stop(timeout=2.0)
        # After stop, thread should be gone
        self.assertFalse(sched.get_stats()["is_running"])

    def test_latest_model_path_none_initially(self):
        sched = self._make_scheduler()
        self.assertIsNone(sched.get_latest_model_path())

    def test_run_once_increments_cycle(self):
        sched = self._make_scheduler()
        result = sched.run_once()
        # When optuna is not installed, result is {"status": "skipped", "reason": "optuna not installed"}
        if result.get("status") == "skipped":
            self.assertIn("optuna", result.get("reason", ""))
        else:
            self.assertEqual(result["cycle"], 1)
        stats = sched.get_stats()
        self.assertEqual(stats["cycle_count"], 1)
        self.assertIsNotNone(stats["last_run"])

    def test_run_once_skips_when_dataset_missing(self):
        sched = self._make_scheduler(data_path="/tmp/nonexistent_automl_dataset.csv")
        result = sched.run_once()
        self.assertEqual(result["status"], "skipped")
        # Reason can be either "dataset not found" or "optuna not installed"
        self.assertTrue(
            "dataset not found" in result.get("reason", "")
            or "optuna" in result.get("reason", ""),
            f"Unexpected skip reason: {result.get('reason')}"
        )


class TestContinuousAutoMLSchedulerWithDataset(TestCase):
    """Test scheduler with a real (small) dataset file."""

    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()
        self._data_path = os.path.join(self._tmpdir, "test_data.csv")
        self._registry_dir = os.path.join(self._tmpdir, "registry")

        # Create minimal CSV dataset
        import pandas as pd
        import numpy as np

        np.random.seed(42)
        df = pd.DataFrame({
            "close": np.cumsum(np.random.randn(200)) + 100,
            "volume": np.random.randint(100, 1000, 200).astype(float),
            "rsi_14": np.random.uniform(20, 80, 200),
            "macd_hist": np.random.randn(200),
            "bb_width": np.random.uniform(0.01, 0.05, 200),
        })
        df.to_csv(self._data_path, index=False)

    def tearDown(self):
        import shutil
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def _make_scheduler(self, **kwargs):
        from src.pipeline.continuous_automl_scheduler import ContinuousAutoMLScheduler

        defaults = dict(
            data_path=self._data_path,
            model_registry_dir=self._registry_dir,
            optuna_trials=2,
            walk_forward_splits=2,
        )
        defaults.update(kwargs)
        return ContinuousAutoMLScheduler(**defaults)

    def test_run_once_completes_or_skips(self):
        sched = self._make_scheduler()
        result = sched.run_once()
        # Should complete or skip gracefully (never crash)
        self.assertIn(
            result["status"],
            {"completed", "optuna_failed", "wf_failed", "skipped"},
        )
        if result["status"] != "skipped":
            self.assertEqual(result["cycle"], 1)

    def test_run_once_with_custom_eval_callback(self):
        """Test that custom eval callback is invoked when optuna available."""
        import importlib
        optuna_available = importlib.util.find_spec("optuna") is not None

        call_count = {"n": 0}

        def custom_eval(params, df):
            call_count["n"] += 1
            return 1.5

        sched = self._make_scheduler(eval_callback=custom_eval)
        result = sched.run_once()
        if optuna_available:
            # Custom callback should have been called at least once
            self.assertGreater(call_count["n"], 0)
        else:
            # Without optuna, scheduler skips — callback not invoked
            self.assertEqual(result["status"], "skipped")

    def test_walk_forward_validation_structure(self):
        """Test walk-forward output structure."""
        from src.pipeline.continuous_automl_scheduler import ContinuousAutoMLScheduler

        sched = self._make_scheduler()
        params = {"learning_rate": 3e-4, "gamma": 0.99, "ent_coef": 0.01}
        wf = sched._walk_forward_validate(params)

        self.assertIn("fold_rewards", wf)
        self.assertIn("mean_reward", wf)
        self.assertIn("std_reward", wf)
        self.assertIn("passed", wf)
        self.assertIn("n_folds", wf)

    def test_promote_model_creates_files(self):
        """Test model promotion creates config.json and latest.json."""
        sched = self._make_scheduler()
        params = {"learning_rate": 3e-4, "gamma": 0.99}
        wf_result = {"mean_reward": 1.5, "std_reward": 0.1, "passed": True}

        path = sched._promote_model(params, wf_result)
        self.assertTrue(os.path.isdir(path))

        config_path = os.path.join(path, "config.json")
        self.assertTrue(os.path.isfile(config_path))

        config = json.loads(Path(config_path).read_text())
        self.assertEqual(config["params"], params)
        self.assertEqual(config["cycle"], 0)

        latest_path = os.path.join(self._registry_dir, "latest.json")
        self.assertTrue(os.path.isfile(latest_path))
        latest = json.loads(Path(latest_path).read_text())
        self.assertIn("latest_model_dir", latest)
        self.assertIn("params", latest)

    def test_promote_model_callback_invoked(self):
        """Test on_model_promoted callback is called."""
        promoted = {"called": False, "path": None}

        def on_promote(path, params, wf):
            promoted["called"] = True
            promoted["path"] = path

        sched = self._make_scheduler(on_model_promoted=on_promote)
        params = {"learning_rate": 3e-4}
        wf_result = {"mean_reward": 2.0, "passed": True}
        sched._promote_model(params, wf_result)

        self.assertTrue(promoted["called"])
        self.assertIsNotNone(promoted["path"])


class TestContinuousAutoMLSchedulerConcurrency(TestCase):
    """Test thread-safety of scheduler operations."""

    def test_stats_thread_safe(self):
        from src.pipeline.continuous_automl_scheduler import ContinuousAutoMLScheduler

        sched = ContinuousAutoMLScheduler(
            data_path="nonexistent.csv",
            optuna_trials=1,
        )
        errors = []

        def read_stats():
            try:
                for _ in range(50):
                    stats = sched.get_stats()
                    self.assertIsInstance(stats, dict)
                    self.assertIn("cycle_count", stats)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=read_stats) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5.0)

        self.assertEqual(len(errors), 0)


if __name__ == "__main__":
    main()