"""End-to-end integration test.

Validates the prepare_data → backtest pipeline using the real BTCUSDT dataset.
Tests only the scripts/components that actually exist in the codebase.

Wave 8: Updated to use actual project scripts instead of removed IDX scripts.
"""

import os
import subprocess
import sys
import unittest

# ensure project root is importable
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

DATASET = os.path.join(ROOT, "data", "dataset", "hf_BTCUSDT_5m.csv")


class EndToEndIntegration(unittest.TestCase):
    """Validate the data pipeline and backtester work end-to-end."""

    @unittest.skipUnless(os.path.exists(DATASET),
                         "hf_BTCUSDT_5m.csv dataset not found")
    def test_backtest_with_live_constraints(self):
        """Run backtester against the BTCUSDT dataset with live constraints."""
        cmd = [
            sys.executable,
            os.path.join(ROOT, "scripts", "backtest_live_constraints.py"),
            "--dataset-csv", DATASET,
            "--symbol", "BTCUSDT",
            "--initial-cash", "10000",
            "--max-drawdown-pct", "0.20",
        ]
        r = subprocess.run(cmd, capture_output=True, text=True, cwd=ROOT, timeout=120)
        self.assertEqual(r.returncode, 0, f"Backtest failed:\n{r.stderr}")
        # Check that output JSON was created
        out_json = os.path.join(ROOT, "data", "backtest_result.json")
        self.assertTrue(os.path.exists(out_json),
                        "backtest_result.json not created")

    @unittest.skipUnless(os.path.exists(DATASET),
                         "hf_BTCUSDT_5m.csv dataset not found")
    def test_prepare_data_pipeline(self):
        """Run prepare_data on the existing BTCUSDT CSV."""
        features_out = os.path.join(ROOT, "data", "dataset",
                                    "integration_features.csv")
        cmd = [
            sys.executable,
            os.path.join(ROOT, "scripts", "prepare_data.py"),
            "--input-csv", DATASET,
            "--symbol", "BTC/USDT",
            "--timeframe", "5m",
            "--features-out", features_out,
            "--max-rows", "5000",
        ]
        r = subprocess.run(cmd, capture_output=True, text=True, cwd=ROOT, timeout=120)
        self.assertEqual(r.returncode, 0, f"prepare_data failed:\n{r.stderr}")
        self.assertTrue(os.path.exists(features_out),
                        f"Feature output not created: {features_out}")
        # Cleanup
        if os.path.exists(features_out):
            os.remove(features_out)


if __name__ == "__main__":
    unittest.main()