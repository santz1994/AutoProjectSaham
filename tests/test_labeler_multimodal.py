import os
import sys
import json
import tempfile
import unittest
from unittest.mock import patch

import pandas as pd

# ensure src package is importable
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


class LabelerMultimodalTests(unittest.TestCase):
    def test_build_dataset_with_multimodal_features(self):
        from src.ml.labeler import build_dataset

        with tempfile.TemporaryDirectory() as td:
            price_dir = os.path.join(td, "prices")
            os.makedirs(price_dir, exist_ok=True)
            out_csv = os.path.join(td, "dataset.csv")

            price_payload = {
                "symbol": "BBCA.JK",
                "prices": [100.0 + (i * 0.5) for i in range(60)],
                "volumes": [1000 + (i * 5) for i in range(60)],
            }
            with open(
                os.path.join(price_dir, "BBCA.JK.json"),
                "w",
                encoding="utf-8",
            ) as file:
                json.dump(price_payload, file)

            etl_payload = {
                "timestamp": "20260406T000000Z",
                "data": {
                    "cot": {
                        "latest": {
                            "cot_index_noncommercial": 80.0,
                            "cot_index_commercial": 30.0,
                            "noncommercial_net": 10000,
                            "commercial_net": -7000,
                        }
                    }
                },
            }
            with open(
                os.path.join(td, "etl_20260406T000000Z.json"),
                "w",
                encoding="utf-8",
            ) as file:
                json.dump(etl_payload, file)

            with patch(
                "src.ml.feature_store._compute_symbol_sentiment_features",
                return_value={
                    "news_sentiment_1d": 0.15,
                    "news_sentiment_7d": 0.25,
                    "news_volume_7d": 7,
                },
            ):
                csv_path = build_dataset(
                    price_dir=price_dir,
                    out_csv=out_csv,
                    short=3,
                    long=5,
                    horizon=4,
                    max_symbols=1,
                    use_triple_barrier=False,
                    use_sample_weights=False,
                    include_multimodal=True,
                    etl_dir=td,
                )

            self.assertEqual(csv_path, out_csv)
            df = pd.read_csv(out_csv)
            self.assertFalse(df.empty)
            self.assertIn("horizon_tag", df.columns)
            self.assertIn("horizon_bars", df.columns)
            self.assertIn("news_sentiment_7d", df.columns)
            self.assertIn("cot_index_noncommercial", df.columns)
            self.assertIn("has_cot_features", df.columns)
            self.assertTrue((df["has_cot_features"] == 1).any())

    def test_build_dataset_triple_barrier_keeps_barrier_columns(self):
        from src.ml.labeler import build_dataset

        with tempfile.TemporaryDirectory() as td:
            price_dir = os.path.join(td, "prices")
            os.makedirs(price_dir, exist_ok=True)
            out_csv = os.path.join(td, "dataset_triple.csv")

            # Monotonic price trend is enough to exercise triple-barrier path.
            price_payload = {
                "symbol": "BBCA.JK",
                "prices": [100.0 + (i * 0.3) for i in range(80)],
                "volumes": [1000 + (i * 4) for i in range(80)],
            }
            with open(
                os.path.join(price_dir, "BBCA.JK.json"),
                "w",
                encoding="utf-8",
            ) as file:
                json.dump(price_payload, file)

            csv_path = build_dataset(
                price_dir=price_dir,
                out_csv=out_csv,
                short=3,
                long=10,
                horizon=5,
                max_symbols=1,
                use_triple_barrier=True,
                use_sample_weights=False,
                include_multimodal=False,
            )

            self.assertEqual(csv_path, out_csv)
            df = pd.read_csv(out_csv)
            self.assertFalse(df.empty)
            self.assertIn("bars_to_exit", df.columns)
            self.assertIn("entry_price", df.columns)
            self.assertTrue(df["bars_to_exit"].notna().all())


if __name__ == "__main__":
    unittest.main()
