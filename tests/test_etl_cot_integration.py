import os
import sys
import unittest
from unittest.mock import patch

# ensure src package is importable
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


class ETLCOTIntegrationTests(unittest.TestCase):
    def test_run_etl_includes_cot_payload(self):
        cot_payload = {
            "market": "EURUSD",
            "n_records": 10,
            "records": [],
            "latest": {},
        }

        with patch(
            "src.pipeline.data_connectors.idx_connector.fetch_idx",
            return_value={"BBCA.JK": []},
        ), patch(
            "src.pipeline.data_connectors.forex_connector.fetch_forex_time_series",
            return_value={"rates": {}},
        ), patch(
            "src.pipeline.data_connectors.news_connector.fetch_news",
            return_value={"articles": []},
        ), patch(
            "src.pipeline.data_connectors.cot_connector.fetch_cot_data",
            return_value=cot_payload,
        ) as mock_cot:
            from src.pipeline.etl import run_etl

            payload = run_etl(["BBCA"], news_api_key="FAKE")

        self.assertIn("cot", payload)
        self.assertNotIn("cot_error", payload)
        self.assertEqual(payload["cot"]["market"], "EURUSD")
        mock_cot.assert_called_once()

    def test_run_etl_sets_cot_error_on_failure(self):
        with patch(
            "src.pipeline.data_connectors.idx_connector.fetch_idx",
            return_value={"BBCA.JK": []},
        ), patch(
            "src.pipeline.data_connectors.forex_connector.fetch_forex_time_series",
            return_value={"rates": {}},
        ), patch(
            "src.pipeline.data_connectors.news_connector.fetch_news",
            return_value={"articles": []},
        ), patch(
            "src.pipeline.data_connectors.cot_connector.fetch_cot_data",
            side_effect=RuntimeError("cot source unavailable"),
        ):
            from src.pipeline.etl import run_etl

            payload = run_etl(["BBCA"], news_api_key="FAKE")

        self.assertIn("cot_error", payload)
        self.assertNotIn("cot", payload)
        self.assertIn("cot source unavailable", payload["cot_error"])


if __name__ == "__main__":
    unittest.main()
