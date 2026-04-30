import os
import sys
import tempfile
import unittest

import numpy as np
import pandas as pd  # type: ignore[import-untyped]


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


def _build_raw_df(rows: int = 500) -> pd.DataFrame:
    base_timestamp = 1_700_000_000_000
    timestamps = np.array([base_timestamp + (i * 300_000) for i in range(rows)])

    trend = np.linspace(45_000.0, 48_000.0, rows)
    oscillation = np.sin(np.arange(rows) / 7.0) * 60.0
    close = trend + oscillation
    open_price = close - (np.cos(np.arange(rows) / 10.0) * 5.0)
    high = np.maximum(open_price, close) + 15.0
    low = np.minimum(open_price, close) - 15.0
    volume = 1_000.0 + ((np.arange(rows) % 40) * 25.0)

    return pd.DataFrame(
        {
            "timestamp": timestamps,
            "datetime": pd.to_datetime(timestamps, unit="ms", utc=True),
            "open": open_price,
            "high": high,
            "low": low,
            "close": close,
            "volume": volume,
        }
    )


class PrepareDataPipelineTests(unittest.TestCase):
    def test_build_feature_dataset_no_nan_inf(self):
        from src.pipeline.prepare_data import build_feature_dataset

        raw_df = _build_raw_df(rows=500)
        feature_df = build_feature_dataset(
            raw_df,
            symbol="BTC/USDT",
            timeframe="5m",
            short_window=5,
            long_window=20,
            horizon_bars=8,
            dropna=True,
        )

        self.assertGreater(len(feature_df), 200)

        required_columns = {
            "symbol",
            "timeframe",
            "timestamp",
            "datetime",
            "last_price",
            "rsi_14",
            "macd",
            "bb_width",
            "dist_to_liquidation",
            "norm_rsi_14",
            "norm_macd",
            "norm_bb_width",
            "norm_dist_to_liquidation",
        }
        self.assertTrue(required_columns.issubset(set(feature_df.columns)))

        numeric_df = feature_df.select_dtypes(include=[np.number])
        self.assertFalse(numeric_df.isna().any().any())
        self.assertTrue(np.isfinite(numeric_df.to_numpy()).all())
        self.assertTrue(pd.Series(feature_df["timestamp"]).is_monotonic_increasing)

    def test_prepare_training_dataset_from_input_csv(self):
        from src.pipeline.prepare_data import prepare_training_dataset

        raw_df = _build_raw_df(rows=450)

        with tempfile.TemporaryDirectory() as temp_dir:
            input_csv = os.path.join(temp_dir, "raw.csv")
            raw_out = os.path.join(temp_dir, "raw_copy.csv")
            features_out = os.path.join(temp_dir, "features.csv")

            raw_df.to_csv(input_csv, index=False)

            summary = prepare_training_dataset(
                input_csv=input_csv,
                raw_out=raw_out,
                features_out=features_out,
                symbol="BTC/USDT",
                timeframe="5m",
                short_window=5,
                long_window=20,
                horizon_bars=8,
                min_required_rows=100,
                max_rows=350,
            )

            self.assertTrue(os.path.exists(raw_out))
            self.assertTrue(os.path.exists(features_out))
            self.assertGreaterEqual(summary["feature_rows"], 100)

            features_df = pd.read_csv(features_out)
            self.assertEqual(len(features_df), summary["feature_rows"])
            self.assertIn("symbol", features_df.columns)
            self.assertIn("timeframe", features_df.columns)
            self.assertIn("norm_dist_to_liquidation", features_df.columns)

            numeric_df = features_df.select_dtypes(include=[np.number])
            self.assertFalse(numeric_df.isna().any().any())
            self.assertTrue(np.isfinite(numeric_df.to_numpy()).all())


if __name__ == "__main__":
    unittest.main()
