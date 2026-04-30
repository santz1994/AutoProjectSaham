import os
import sys
import tempfile
import unittest
from unittest.mock import patch

import pandas as pd

# ensure src package is importable
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


class TrainerMultimodalTests(unittest.TestCase):
    def test_train_model_accepts_categorical_horizon_tag(self):
        from src.ml.trainer import train_model

        with tempfile.TemporaryDirectory() as td:
            dataset_csv = os.path.join(td, "dataset.csv")
            model_out = os.path.join(td, "model.joblib")

            rows = []
            for i in range(40):
                rows.append(
                    {
                        "symbol": "BBCA.JK",
                        "t_index": i,
                        "future_return": 0.01 if i % 2 == 0 else -0.01,
                        "label": 1 if i % 3 == 0 else 0,
                        "last_price": 100 + i,
                        "short_sma": 99 + i,
                        "long_sma": 98 + i,
                        "volatility": 0.02,
                        "momentum": 0.01,
                        "horizon_tag": "short_term" if i < 20 else "medium_term",
                        "horizon_bars": 5,
                        "has_cot_features": 1,
                        "has_sentiment_features": 0,
                    }
                )

            pd.DataFrame(rows).to_csv(dataset_csv, index=False)

            result = train_model(
                dataset_csv=dataset_csv,
                model_out=model_out,
                use_optuna=False,
                enable_multimodal=False,
                test_size=0.2,
                purge_gap=2,
            )

            self.assertEqual(result["model_path"], model_out)
            self.assertIn("report", result)
            self.assertTrue(os.path.exists(model_out))

    def test_train_model_skips_duplicate_multimodal_augmentation(self):
        from src.ml.trainer import train_model

        with tempfile.TemporaryDirectory() as td:
            dataset_csv = os.path.join(td, "dataset_with_multi.csv")
            model_out = os.path.join(td, "model_with_multi.joblib")

            rows = []
            for i in range(30):
                rows.append(
                    {
                        "symbol": "BBCA.JK",
                        "t_index": i,
                        "future_return": 0.01 if i % 2 == 0 else -0.01,
                        "label": 1 if i % 4 == 0 else 0,
                        "last_price": 100 + i,
                        "short_sma": 99 + i,
                        "long_sma": 98 + i,
                        "volatility": 0.02,
                        "momentum": 0.01,
                        "horizon_tag": "short_term",
                        "horizon_bars": 5,
                        "has_cot_features": 1,
                        "has_sentiment_features": 0,
                    }
                )

            pd.DataFrame(rows).to_csv(dataset_csv, index=False)

            with patch(
                "src.ml.feature_store.augment_dataset_with_multimodal",
                side_effect=AssertionError("multimodal augmentation should be skipped"),
            ):
                result = train_model(
                    dataset_csv=dataset_csv,
                    model_out=model_out,
                    use_optuna=False,
                    enable_multimodal=True,
                    test_size=0.2,
                    purge_gap=2,
                )

            self.assertEqual(result["model_path"], model_out)
            self.assertTrue(os.path.exists(model_out))

    def test_train_model_handles_multiclass_roc_auc(self):
        from src.ml.trainer import train_model

        with tempfile.TemporaryDirectory() as td:
            dataset_csv = os.path.join(td, "dataset_multiclass.csv")
            model_out = os.path.join(td, "model_multiclass.joblib")

            rows = []
            labels = [-1, 0, 1]
            for i in range(60):
                rows.append(
                    {
                        "symbol": "BBCA.JK",
                        "t_index": i,
                        "future_return": 0.01 if i % 2 == 0 else -0.01,
                        "label": labels[i % 3],
                        "last_price": 100 + i,
                        "short_sma": 99 + i,
                        "long_sma": 98 + i,
                        "volatility": 0.02,
                        "momentum": 0.01,
                    }
                )

            pd.DataFrame(rows).to_csv(dataset_csv, index=False)

            result = train_model(
                dataset_csv=dataset_csv,
                model_out=model_out,
                use_optuna=False,
                enable_multimodal=False,
                test_size=0.2,
                purge_gap=2,
            )

            self.assertEqual(result["model_path"], model_out)
            self.assertIn("roc_auc", result)
            self.assertTrue(os.path.exists(model_out))

    def test_train_model_forwards_finbert_settings(self):
        from src.ml.trainer import train_model

        with tempfile.TemporaryDirectory() as td:
            dataset_csv = os.path.join(td, "dataset_finbert.csv")
            model_out = os.path.join(td, "model_finbert.joblib")

            rows = []
            for i in range(40):
                rows.append(
                    {
                        "symbol": "BBCA.JK",
                        "t_index": i,
                        "future_return": 0.01 if i % 2 == 0 else -0.01,
                        "label": 1 if i % 3 == 0 else 0,
                        "last_price": 100 + i,
                        "short_sma": 99 + i,
                        "long_sma": 98 + i,
                        "volatility": 0.02,
                        "momentum": 0.01,
                    }
                )

            pd.DataFrame(rows).to_csv(dataset_csv, index=False)

            with patch(
                "src.ml.feature_store.augment_dataset_with_multimodal",
                side_effect=lambda df, **_: df,
            ) as mocked_augment:
                result = train_model(
                    dataset_csv=dataset_csv,
                    model_out=model_out,
                    use_optuna=False,
                    enable_multimodal=True,
                    test_size=0.2,
                    purge_gap=2,
                    use_finbert=True,
                    finbert_model="ProsusAI/finbert",
                    finbert_device=0,
                )

            self.assertEqual(result["model_path"], model_out)
            self.assertTrue(mocked_augment.called)
            kwargs = mocked_augment.call_args.kwargs
            self.assertTrue(kwargs["use_finbert"])
            self.assertEqual(kwargs["finbert_model"], "ProsusAI/finbert")
            self.assertEqual(kwargs["finbert_device"], 0)


if __name__ == "__main__":
    unittest.main()
