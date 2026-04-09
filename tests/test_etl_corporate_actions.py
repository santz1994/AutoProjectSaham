import json
import os
import tempfile
import unittest
from unittest.mock import patch

import pandas as pd  # type: ignore[import-untyped]

from src.pipeline.corporate_actions import apply_corporate_actions_to_ohlcv
from src.pipeline.etl import run_etl


class CorporateActionAdjustmentTests(unittest.TestCase):
    def _sample_split_frame(self):
        idx = pd.to_datetime(["2024-01-01", "2024-01-02", "2024-01-03"])
        return pd.DataFrame(
            {
                "Open": [100.0, 102.0, 50.0],
                "High": [101.0, 103.0, 51.0],
                "Low": [99.0, 101.0, 49.0],
                "Close": [100.0, 102.0, 50.0],
                "Volume": [1000, 1200, 1500],
            },
            index=idx,
        )

    def test_apply_split_backward_adjustment(self):
        frame = self._sample_split_frame()
        adjusted = apply_corporate_actions_to_ohlcv(
            frame,
            [
                {
                    "symbol": "BBCA",
                    "ex_date": "2024-01-03",
                    "action_type": "split",
                    "ratio": 2,
                }
            ],
        )

        self.assertAlmostEqual(float(adjusted.iloc[0]["Close"]), 50.0, places=6)
        self.assertAlmostEqual(float(adjusted.iloc[1]["Close"]), 51.0, places=6)
        self.assertAlmostEqual(float(adjusted.iloc[2]["Close"]), 50.0, places=6)

        self.assertEqual(int(adjusted.iloc[0]["Volume"]), 2000)
        self.assertEqual(int(adjusted.iloc[1]["Volume"]), 2400)
        self.assertEqual(int(adjusted.iloc[2]["Volume"]), 1500)

    def test_apply_dividend_backward_adjustment(self):
        idx = pd.to_datetime(["2024-01-01", "2024-01-02", "2024-01-03"])
        frame = pd.DataFrame(
            {
                "Open": [100.0, 100.0, 95.0],
                "High": [101.0, 101.0, 96.0],
                "Low": [99.0, 99.0, 94.0],
                "Close": [100.0, 100.0, 95.0],
                "Volume": [1000, 1000, 1300],
            },
            index=idx,
        )

        adjusted = apply_corporate_actions_to_ohlcv(
            frame,
            [
                {
                    "symbol": "BBCA",
                    "ex_date": "2024-01-03",
                    "action_type": "dividend",
                    "value": 5.0,
                }
            ],
        )

        self.assertAlmostEqual(float(adjusted.iloc[0]["Close"]), 95.0, places=6)
        self.assertAlmostEqual(float(adjusted.iloc[1]["Close"]), 95.0, places=6)
        self.assertAlmostEqual(float(adjusted.iloc[2]["Close"]), 95.0, places=6)
        self.assertEqual(int(adjusted.iloc[0]["Volume"]), 1000)

    def test_run_etl_applies_corporate_actions_file(self):
        frame = self._sample_split_frame()

        with tempfile.NamedTemporaryFile("w", delete=False, suffix=".json") as tmp:
            json.dump(
                {
                    "actions": [
                        {
                            "symbol": "BBCA",
                            "ex_date": "2024-01-03",
                            "action_type": "split",
                            "ratio": 2,
                        }
                    ]
                },
                tmp,
            )
            action_file = tmp.name

        try:
            with patch(
                "src.pipeline.data_connectors.idx_connector.fetch_idx",
                return_value={"BBCA.JK": frame},
            ), patch(
                "src.pipeline.data_connectors.forex_connector.fetch_forex_time_series",
                return_value={"rates": {}},
            ), patch(
                "src.pipeline.data_connectors.news_connector.fetch_news",
                return_value={"articles": []},
            ), patch(
                "src.pipeline.data_connectors.cot_connector.fetch_cot_data",
                return_value={"market": "EURUSD", "records": []},
            ):
                payload = run_etl(
                    ["BBCA"],
                    news_api_key="FAKE",
                    corporate_actions_path=action_file,
                )
        finally:
            os.remove(action_file)

        adjusted_frame = payload["stocks"]["BBCA.JK"]
        self.assertAlmostEqual(float(adjusted_frame.iloc[0]["Close"]), 50.0, places=6)

        summary = payload.get("stocks_corporate_actions", {})
        self.assertTrue(summary.get("applied"))
        self.assertIn("BBCA", summary.get("appliedSymbols", []))


if __name__ == "__main__":
    unittest.main()
