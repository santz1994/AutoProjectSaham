import os
import sys
import unittest

# ensure src package is importable
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


class TestOHLCVValidation(unittest.TestCase):
    def test_valid_rows(self):
        rows = [
            {
                "Date": "2026-03-30",
                "Open": 100.0,
                "High": 110.0,
                "Low": 95.0,
                "Close": 105.0,
                "Adj Close": 105.0,
                "Volume": 1000,
            },
            {
                "date": "2026-03-31",
                "open": 105.0,
                "high": 112.0,
                "low": 101.0,
                "close": 110.0,
                "adj_close": 110.0,
                "volume": 2000,
            },
        ]
        from src.pipeline.data_connectors.schemas import validate_ohlcv_rows

        self.assertTrue(validate_ohlcv_rows(rows))

    def test_invalid_high_low(self):
        rows = [
            {
                "Date": "2026-03-30",
                "Open": 100.0,
                "High": 90.0,
                "Low": 95.0,
                "Close": 92.0,
            },
        ]
        with self.assertRaises(ValueError):
            from src.pipeline.data_connectors.schemas import validate_ohlcv_rows

            validate_ohlcv_rows(rows)


if __name__ == "__main__":
    unittest.main()
