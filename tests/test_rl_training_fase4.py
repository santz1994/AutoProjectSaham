"""Tests for Fase 4: Deep RL Training Script (train_crypto_rl.py).

Validates:
- SB3TradingEnvWrapper interface (reset, step, spaces)
- _load_dataset and _extract_price_volume helpers
- Full train() pipeline with small synthetic dataset + few timesteps
- Checkpoint resume logic
"""
from __future__ import annotations

import os
import json
import tempfile
import unittest
from unittest.mock import patch, MagicMock

import numpy as np
import pandas as pd

from scripts.train_crypto_rl import (
    SB3TradingEnvWrapper,
    _load_dataset,
    _extract_price_volume,
    _set_seeds,
)


def _make_synthetic_dataset(n: int = 200, symbol: str = "BTC/USDT") -> pd.DataFrame:
    """Create a minimal feature dataset for testing."""
    np.random.seed(42)
    base_price = 50_000.0
    returns = np.random.normal(0.0001, 0.01, n)
    prices = base_price * np.cumprod(1.0 + returns)

    df = pd.DataFrame({
        "symbol": symbol,
        "timeframe": "5m",
        "timestamp": np.arange(n) * 300_000 + 1_700_000_000_000,
        "datetime": pd.date_range("2024-01-01", periods=n, freq="5min", tz="UTC"),
        "last_price": prices,
        "close": prices,
        "volume": np.random.uniform(100, 1000, n),
        "open": prices * 0.999,
        "high": prices * 1.002,
        "low": prices * 0.998,
        "rsi_14": np.random.uniform(20, 80, n),
        "macd": np.random.normal(0, 10, n),
        "bb_width": np.random.uniform(100, 500, n),
        "dist_to_liquidation": np.random.uniform(0.01, 0.5, n),
        "norm_rsi_14": np.random.uniform(-1, 1, n),
        "norm_macd": np.random.uniform(-1, 1, n),
        "norm_bb_width": np.random.uniform(-1, 1, n),
        "norm_dist_to_liquidation": np.random.uniform(-1, 1, n),
    })
    return df


class TestSB3TradingEnvWrapper(unittest.TestCase):
    """Test the SB3-compatible env wrapper."""

    def setUp(self):
        np.random.seed(42)
        self.prices = [100.0 + i * 0.1 + np.random.normal(0, 0.5) for i in range(200)]
        self.volumes = [float(np.random.uniform(10, 100)) for _ in range(200)]

    def test_wrapper_init(self):
        wrapper = SB3TradingEnvWrapper(
            prices=self.prices,
            volumes=self.volumes,
            symbol="BTC/USDT",
        )
        self.assertIsNotNone(wrapper.inner)
        # action_space and observation_space may or may not be set depending on gym availability

    def test_reset_returns_obs_and_info(self):
        wrapper = SB3TradingEnvWrapper(
            prices=self.prices,
            volumes=self.volumes,
        )
        out = wrapper.reset()
        self.assertIsInstance(out, tuple)
        self.assertEqual(len(out), 2)  # (obs, info)
        obs, info = out
        self.assertIsInstance(obs, (np.ndarray, list, float))

    def test_step_returns_5_tuple(self):
        wrapper = SB3TradingEnvWrapper(
            prices=self.prices,
            volumes=self.volumes,
        )
        wrapper.reset()
        action = [1, 2]  # BUY with TP level 2
        out = wrapper.step(action)
        self.assertIsInstance(out, tuple)
        self.assertEqual(len(out), 5)  # obs, reward, terminated, truncated, info
        obs, reward, terminated, truncated, info = out
        self.assertIsInstance(reward, float)
        self.assertIsInstance(terminated, bool)
        self.assertIsInstance(truncated, bool)

    def test_multiple_steps(self):
        wrapper = SB3TradingEnvWrapper(
            prices=self.prices,
            volumes=self.volumes,
        )
        wrapper.reset()
        done = False
        steps = 0
        while not done and steps < 50:
            action = [np.random.randint(0, 4), np.random.randint(0, 5)]
            obs, reward, terminated, truncated, info = wrapper.step(action)
            done = terminated or truncated
            steps += 1
        self.assertGreater(steps, 0)

    def test_close_does_not_raise(self):
        wrapper = SB3TradingEnvWrapper(
            prices=self.prices,
        )
        wrapper.close()  # Should not raise


class TestHelpers(unittest.TestCase):
    """Test helper functions."""

    def test_load_dataset_csv(self):
        df = _make_synthetic_dataset(100)
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False, mode="w") as f:
            df.to_csv(f, index=False)
            path = f.name
        try:
            loaded = _load_dataset(path)
            self.assertEqual(len(loaded), 100)
            self.assertIn("close", loaded.columns)
        finally:
            os.unlink(path)

    def test_load_dataset_uses_last_price_as_close(self):
        df = _make_synthetic_dataset(50)
        df = df.drop(columns=["close"])
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False, mode="w") as f:
            df.to_csv(f, index=False)
            path = f.name
        try:
            loaded = _load_dataset(path)
            self.assertIn("close", loaded.columns)
            np.testing.assert_array_almost_equal(
                loaded["close"].values,
                df["last_price"].values,
            )
        finally:
            os.unlink(path)

    def test_load_dataset_missing_file(self):
        with self.assertRaises(FileNotFoundError):
            _load_dataset("/nonexistent/path/data.csv")

    def test_load_dataset_missing_close_column(self):
        df = pd.DataFrame({"open": [1, 2], "high": [3, 4]})
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False, mode="w") as f:
            df.to_csv(f, index=False)
            path = f.name
        try:
            with self.assertRaises(ValueError):
                _load_dataset(path)
        finally:
            os.unlink(path)

    def test_extract_price_volume(self):
        df = _make_synthetic_dataset(100)
        prices, volumes = _extract_price_volume(df)
        self.assertEqual(len(prices), 100)
        self.assertEqual(len(volumes), 100)
        self.assertIsInstance(prices[0], float)

    def test_extract_price_volume_no_volume_column(self):
        df = _make_synthetic_dataset(50)
        df = df.drop(columns=["volume"])
        prices, volumes = _extract_price_volume(df)
        self.assertEqual(len(volumes), 50)
        self.assertEqual(volumes[0], 0.0)

    def test_set_seeds_deterministic(self):
        _set_seeds(12345)
        a = np.random.random()
        _set_seeds(12345)
        b = np.random.random()
        self.assertEqual(a, b)


class TestTrainPipeline(unittest.TestCase):
    """Test the full training pipeline with minimal timesteps."""

    def test_train_ppo_short(self):
        """Smoke test: train PPO for 512 steps on synthetic data."""
        df = _make_synthetic_dataset(300)
        with tempfile.TemporaryDirectory() as tmpdir:
            dataset_path = os.path.join(tmpdir, "test_data.csv")
            df.to_csv(dataset_path, index=False)

            model_out = os.path.join(tmpdir, "test_model.zip")

            from scripts.train_crypto_rl import train

            summary = train(
                dataset_path=dataset_path,
                symbol="BTC/USDT",
                total_timesteps=512,
                algorithm="ppo",
                n_steps=128,
                batch_size=64,
                n_epochs=2,
                learning_rate=1e-3,
                starting_cash=10_000.0,
                max_leverage=10.0,
                checkpoint_dir=os.path.join(tmpdir, "ckpts"),
                checkpoint_freq=256,
                model_out=model_out,
                tensorboard_log=os.path.join(tmpdir, "tb"),
                seed=42,
                device="cpu",
                train_split=0.8,
            )

            # Verify outputs
            self.assertIn("model_path", summary)
            self.assertIn("final_mean_reward", summary)
            self.assertEqual(summary["algorithm"], "ppo")
            self.assertEqual(summary["symbol"], "BTC/USDT")
            self.assertTrue(os.path.exists(summary["model_path"]))

            # Config file should exist
            config_path = summary["config_path"]
            self.assertTrue(os.path.exists(config_path))
            with open(config_path) as f:
                cfg = json.load(f)
            self.assertEqual(cfg["algorithm"], "ppo")

            # Summary file should exist
            summary_path = os.path.splitext(model_out)[0] + "_summary.json"
            self.assertTrue(os.path.exists(summary_path))

    def test_train_sac_short(self):
        """Smoke test: train SAC for 512 steps on synthetic data."""
        df = _make_synthetic_dataset(300)
        with tempfile.TemporaryDirectory() as tmpdir:
            dataset_path = os.path.join(tmpdir, "test_data.csv")
            df.to_csv(dataset_path, index=False)

            model_out = os.path.join(tmpdir, "test_sac_model.zip")

            from scripts.train_crypto_rl import train

            summary = train(
                dataset_path=dataset_path,
                symbol="ETH/USDT",
                total_timesteps=512,
                algorithm="sac",
                batch_size=64,
                learning_rate=1e-3,
                starting_cash=5_000.0,
                max_leverage=5.0,
                checkpoint_dir=os.path.join(tmpdir, "ckpts"),
                model_out=model_out,
                tensorboard_log=os.path.join(tmpdir, "tb"),
                seed=42,
                device="cpu",
                train_split=0.8,
            )

            self.assertEqual(summary["algorithm"], "sac")
            self.assertEqual(summary["symbol"], "ETH/USDT")
            self.assertTrue(os.path.exists(summary["model_path"]))

    def test_train_with_leverage_and_fees(self):
        """Verify training works with high leverage and realistic fees."""
        df = _make_synthetic_dataset(300)
        with tempfile.TemporaryDirectory() as tmpdir:
            dataset_path = os.path.join(tmpdir, "test_data.csv")
            df.to_csv(dataset_path, index=False)

            from scripts.train_crypto_rl import train

            summary = train(
                dataset_path=dataset_path,
                total_timesteps=256,
                algorithm="ppo",
                n_steps=64,
                batch_size=32,
                n_epochs=2,
                commission_pct=0.001,
                slippage_pct=0.0005,
                max_leverage=50.0,
                maintenance_margin_fraction=0.10,
                checkpoint_dir=os.path.join(tmpdir, "ckpts"),
                model_out=os.path.join(tmpdir, "model.zip"),
                tensorboard_log=os.path.join(tmpdir, "tb"),
                seed=42,
                device="cpu",
            )

            self.assertEqual(summary["max_leverage"], 50.0)
            self.assertTrue(os.path.exists(summary["model_path"]))

    def test_dataset_too_small_raises(self):
        """Training should fail if dataset is too small for split."""
        df = _make_synthetic_dataset(50)
        with tempfile.TemporaryDirectory() as tmpdir:
            dataset_path = os.path.join(tmpdir, "tiny.csv")
            df.to_csv(dataset_path, index=False)

            from scripts.train_crypto_rl import train

            with self.assertRaises(ValueError):
                train(
                    dataset_path=dataset_path,
                    total_timesteps=256,
                    train_split=0.99,  # Split makes train set < 100
                    checkpoint_dir=os.path.join(tmpdir, "ckpts"),
                    model_out=os.path.join(tmpdir, "model.zip"),
                    tensorboard_log=os.path.join(tmpdir, "tb"),
                    device="cpu",
                )


if __name__ == "__main__":
    unittest.main()