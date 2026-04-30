import os
import sys
import unittest
import json
import tempfile
from unittest.mock import patch

import pandas as pd  # type: ignore[import-untyped]

# ensure src package is importable
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


class FeatureStoreTests(unittest.TestCase):
    def test_basic_features(self):
        from src.ml.feature_store import compute_latest_features

        prices = [100.0 + i for i in range(20)]
        feats = compute_latest_features(prices)
        self.assertIsInstance(feats, dict)
        self.assertAlmostEqual(feats["last_price"], prices[-1])
        self.assertIn("rsi_14", feats)
        self.assertIn("macd", feats)
        self.assertIn("bb_upper", feats)

    def test_avg_vol(self):
        from src.ml.feature_store import compute_latest_features

        prices = [10.0 + i * 0.1 for i in range(10)]
        volumes = [1000 for _ in prices]
        feats = compute_latest_features(prices, volumes=volumes)
        self.assertEqual(feats["avg_vol_5"], 1000.0)

    def test_build_multimodal_feature_row_with_sentiment_and_cot(self):
        from src.ml.feature_store import build_multimodal_feature_row

        prices = [100.0 + i * 0.5 for i in range(30)]
        volumes = [1000 + (i * 10) for i in range(30)]
        sentiment = {
            "news_sentiment_1d": 0.2,
            "news_sentiment_7d": 0.35,
            "news_volume_7d": 11,
        }
        cot = {
            "latest": {
                "cot_index_noncommercial": 82.5,
                "cot_index_commercial": 18.0,
                "noncommercial_net": 24000,
                "commercial_net": -21000,
            }
        }

        row = build_multimodal_feature_row(
            symbol="BTC-USD",
            prices=prices,
            volumes=volumes,
            sentiment_features=sentiment,
            cot_payload=cot,
            horizon="swing",
            horizon_bars=8,
        )

        self.assertEqual(row["symbol"], "BTC-USD")
        self.assertEqual(row["horizon"], "swing")
        self.assertIn("last_price", row)
        self.assertIn("news_sentiment_7d", row)
        self.assertIn("cot_index_noncommercial", row)
        self.assertIn("cot_index_spread", row)
        self.assertIn("horizon_return", row)
        self.assertIn("horizon_volatility", row)
        self.assertEqual(row["horizon_bars"], 8)
        self.assertEqual(row["has_sentiment_features"], 1)
        self.assertEqual(row["has_cot_features"], 1)

    def test_build_multimodal_feature_row_without_optional_modalities(self):
        from src.ml.feature_store import build_multimodal_feature_row

        prices = [90.0 + i for i in range(12)]
        row = build_multimodal_feature_row(
            symbol="ETH-USD",
            prices=prices,
            volumes=None,
        )

        self.assertEqual(row["symbol"], "ETH-USD")
        self.assertEqual(row["has_sentiment_features"], 0)
        self.assertEqual(row["has_cot_features"], 0)

    def test_augment_dataset_with_multimodal(self):
        from src.ml.feature_store import augment_dataset_with_multimodal

        with tempfile.TemporaryDirectory() as td:
            price_dir = os.path.join(td, "prices")
            os.makedirs(price_dir, exist_ok=True)

            price_payload = {
                "symbol": "BTC-USD",
                "prices": [100.0 + i for i in range(40)],
                "volumes": [1000 + i * 10 for i in range(40)],
            }
            with open(
                os.path.join(price_dir, "BTC-USD.json"),
                "w",
                encoding="utf-8",
            ) as file:
                json.dump(price_payload, file)

            etl_payload = {
                "timestamp": "20260406T000000Z",
                "data": {
                    "cot": {
                        "latest": {
                            "cot_index_noncommercial": 78.0,
                            "cot_index_commercial": 25.0,
                            "noncommercial_net": 15000,
                            "commercial_net": -9000,
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

            df = pd.DataFrame(
                {
                    "symbol": ["BTC-USD", "BTC-USD", "AAPL"],
                    "label": [1, 0, 1],
                    "future_return": [0.01, -0.02, 0.03],
                }
            )

            with patch(
                "src.ml.feature_store._compute_symbol_sentiment_features",
                return_value={
                    "news_sentiment_1d": 0.2,
                    "news_sentiment_7d": 0.35,
                    "news_volume_7d": 9,
                },
            ):
                out = augment_dataset_with_multimodal(
                    df,
                    price_dir=price_dir,
                    etl_dir=td,
                    horizon_bars=5,
                )

            self.assertIn("horizon_tag", out.columns)
            self.assertIn("horizon_bars", out.columns)
            self.assertIn("horizon_return", out.columns)
            self.assertIn("horizon_volatility", out.columns)
            self.assertIn("has_sentiment_features", out.columns)
            self.assertIn("has_cot_features", out.columns)
            self.assertIn("cot_index_noncommercial", out.columns)

            crypto_rows = out[out["symbol"] == "BTC-USD"]
            self.assertTrue((crypto_rows["has_sentiment_features"] == 1).all())
            self.assertTrue((crypto_rows["has_cot_features"] == 1).all())
            self.assertEqual(crypto_rows["horizon_tag"].iloc[0], "short_term")
            self.assertTrue(crypto_rows["horizon_return"].notna().all())

    def test_augment_dataset_forwards_finbert_settings(self):
        from src.ml.feature_store import augment_dataset_with_multimodal

        with tempfile.TemporaryDirectory() as td:
            price_dir = os.path.join(td, "prices")
            os.makedirs(price_dir, exist_ok=True)

            with open(
                os.path.join(price_dir, "BTC-USD.json"),
                "w",
                encoding="utf-8",
            ) as file:
                json.dump(
                    {
                        "symbol": "BTC-USD",
                        "prices": [100.0 + i for i in range(20)],
                        "volumes": [1000 + i for i in range(20)],
                    },
                    file,
                )

            df = pd.DataFrame(
                {
                    "symbol": ["BTC-USD"],
                    "label": [1],
                    "future_return": [0.01],
                }
            )

            with patch(
                "src.ml.feature_store._compute_symbol_sentiment_features",
                return_value={"news_sentiment_1d": 0.1},
            ) as mocked_sentiment:
                augment_dataset_with_multimodal(
                    df,
                    price_dir=price_dir,
                    etl_dir=td,
                    horizon_bars=5,
                    use_finbert=True,
                    finbert_model="ProsusAI/finbert",
                    finbert_device=0,
                )

            self.assertTrue(mocked_sentiment.called)
            kwargs = mocked_sentiment.call_args.kwargs
            self.assertTrue(kwargs["use_finbert"])
            self.assertEqual(kwargs["finbert_model"], "ProsusAI/finbert")
            self.assertEqual(kwargs["finbert_device"], 0)


if __name__ == "__main__":
    unittest.main()
