import os
import sys
import unittest

import numpy as np
import pandas as pd  # type: ignore[import-untyped]


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

DATASET_PATH = os.path.join(ROOT, "data", "dataset", "hf_BTCUSDT_5m.csv")


class FeatureStorePhase2Tests(unittest.TestCase):
    def _load_hf_dataframe(self) -> pd.DataFrame:
        if not os.path.exists(DATASET_PATH):
            self.skipTest("HF dataset not found: data/dataset/hf_BTCUSDT_5m.csv")

        df = pd.read_csv(DATASET_PATH)
        required_cols = {"close", "volume"}
        if not required_cols.issubset(set(df.columns)):
            self.skipTest("HF dataset missing required columns: close, volume")

        return df.tail(5000).reset_index(drop=True)

    def test_phase2_indicators_and_normalization(self) -> None:
        from src.ml.feature_store import compute_latest_features

        df = self._load_hf_dataframe()
        prices = df["close"].astype(float).tolist()
        volumes = df["volume"].astype(float).tolist()

        features = compute_latest_features(
            prices=prices,
            volumes=volumes,
            short=5,
            long=20,
            entry_price=float(prices[0]),
            leverage=20.0,
            maintenance_margin_rate=0.005,
            position_side="long",
            include_normalized=True,
        )

        required = [
            "rsi_14",
            "macd",
            "macd_signal",
            "bb_width",
            "dist_to_liquidation",
            "norm_rsi_14",
            "norm_macd",
            "norm_bb_width",
            "norm_dist_to_liquidation",
        ]
        for key in required:
            self.assertIn(key, features)
            self.assertTrue(np.isfinite(float(features[key])))

        norm_values = [
            float(value)
            for key, value in features.items()
            if key.startswith("norm_") and isinstance(value, (int, float, np.number))
        ]
        self.assertGreater(len(norm_values), 0)
        self.assertTrue(all(-1.0001 <= value <= 1.0001 for value in norm_values))

    def test_multimodal_row_no_nan_inf(self) -> None:
        from src.ml.feature_store import build_multimodal_feature_row

        df = self._load_hf_dataframe().tail(1500)
        prices = df["close"].astype(float).tolist()
        volumes = df["volume"].astype(float).tolist()

        row = build_multimodal_feature_row(
            symbol="BTC-USD",
            prices=prices,
            volumes=volumes,
            horizon="short_term",
            horizon_bars=8,
        )

        self.assertIn("dist_to_liquidation", row)
        self.assertIn("norm_dist_to_liquidation", row)
        self.assertIn("norm_horizon_return", row)

        numeric_values = [
            float(value)
            for value in row.values()
            if isinstance(value, (int, float, np.number))
        ]
        self.assertTrue(all(np.isfinite(item) for item in numeric_values))


if __name__ == "__main__":
    unittest.main()
