import os
import sys
import unittest

# ensure src package is importable (same pattern as other tests)
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


class DataConnectorSchemasTests(unittest.TestCase):
    def test_valid_series(self):
        from src.pipeline.data_connectors.schemas import validate_price_series

        self.assertTrue(validate_price_series([100.0, 101.5, 102.3]))

    def test_empty_series_rejected(self):
        from src.pipeline.data_connectors.schemas import validate_price_series

        with self.assertRaises(ValueError):
            validate_price_series([])

    def test_non_numeric_rejected(self):
        from src.pipeline.data_connectors.schemas import validate_price_series

        with self.assertRaises(ValueError):
            validate_price_series([100.0, "N/A"])

    def test_negative_price_rejected(self):
        from src.pipeline.data_connectors.schemas import validate_price_series

        with self.assertRaises(ValueError):
            validate_price_series([100.0, -5.0])


if __name__ == "__main__":
    unittest.main()
