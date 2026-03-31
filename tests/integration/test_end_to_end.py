import os
import subprocess
import sys
import unittest

# ensure project root is importable
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


class EndToEndIntegration(unittest.TestCase):
    def test_generate_train_backtest(self):
        # generate a small demo file for backtester
        cmd = [
            sys.executable,
            os.path.join("bin", "runner.py"),
            "scripts/generate_demo_prices.py",
            "--",
            "--symbols",
            "BBCA.JK",
            "--n",
            "150",
        ]
        r = subprocess.run(cmd, check=True)
        self.assertEqual(r.returncode, 0)

        # run backtester (reads data/prices/BBCA.JK.json)
        cmd = [
            sys.executable,
            os.path.join("bin", "runner.py"),
            "scripts/test_backtester.py",
        ]
        r = subprocess.run(cmd, check=True)
        self.assertEqual(r.returncode, 0)

        # run supervised trainer on the generated file (limit 1)
        out_ds = "data/dataset/integration_dataset.csv"
        out_model = "models/integration_model.joblib"
        cmd = [
            sys.executable,
            os.path.join("bin", "runner.py"),
            "scripts/train_model.py",
            "--",
            "--limit",
            "1",
            "--out-dataset",
            out_ds,
            "--model-out",
            out_model,
        ]
        r = subprocess.run(cmd, check=True)
        self.assertEqual(r.returncode, 0)
        self.assertTrue(os.path.exists(out_ds))
        self.assertTrue(os.path.exists(out_model))


if __name__ == "__main__":
    unittest.main()
