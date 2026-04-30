import os
import sys
import unittest
from unittest.mock import Mock, patch

# ensure src package is importable
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


class COTConnectorTests(unittest.TestCase):
    def test_fetch_cot_data_parses_and_computes_indices(self):
        csv_payload = (
            "Report_Date_as_YYYY-MM-DD,Market_and_Exchange_Names,"
            "Noncommercial_Positions_Long_All,"
            "Noncommercial_Positions_Short_All,"
            "Commercial_Positions_Long_All,Commercial_Positions_Short_All\n"
            "2026-03-03,EURO FX - CHICAGO MERCANTILE EXCHANGE,"
            "180000,120000,110000,150000\n"
            "2026-03-10,EURO FX - CHICAGO MERCANTILE EXCHANGE,"
            "185000,118000,108000,152000\n"
            "2026-03-17,EURO FX - CHICAGO MERCANTILE EXCHANGE,"
            "178000,125000,112000,149000\n"
        )
        mock_resp = Mock()
        mock_resp.status_code = 200
        mock_resp.text = csv_payload
        mock_resp.raise_for_status = lambda: None

        with patch("requests.get", return_value=mock_resp):
            from src.pipeline.data_connectors.cot_connector import fetch_cot_data

            result = fetch_cot_data(market="EURUSD", lookback_weeks=3)

        self.assertEqual(result["market"], "EURUSD")
        self.assertEqual(result["n_records"], 3)
        self.assertIn("latest", result)
        self.assertIn("records", result)

        latest = result["latest"]
        self.assertIn("cot_index_noncommercial", latest)
        self.assertIn("cot_index_commercial", latest)
        self.assertGreaterEqual(latest["cot_index_noncommercial"], 0.0)
        self.assertLessEqual(latest["cot_index_noncommercial"], 100.0)

    def test_fetch_cot_data_no_match_raises(self):
        csv_payload = (
            "Report_Date_as_YYYY-MM-DD,Market_and_Exchange_Names,"
            "Noncommercial_Positions_Long_All,"
            "Noncommercial_Positions_Short_All,"
            "Commercial_Positions_Long_All,Commercial_Positions_Short_All\n"
            "2026-03-03,EURO FX - CHICAGO MERCANTILE EXCHANGE,"
            "180000,120000,110000,150000\n"
        )
        mock_resp = Mock()
        mock_resp.status_code = 200
        mock_resp.text = csv_payload
        mock_resp.raise_for_status = lambda: None

        with patch("requests.get", return_value=mock_resp):
            from src.pipeline.data_connectors.cot_connector import fetch_cot_data

            with self.assertRaises(RuntimeError):
                fetch_cot_data(market="USDJPY", lookback_weeks=4)


if __name__ == "__main__":
    unittest.main()
