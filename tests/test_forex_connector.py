import unittest
import os
import sys
from unittest.mock import patch, Mock

# ensure src package is importable
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from src.pipeline.data_connectors.forex_connector import fetch_forex_time_series


class ForexConnectorTests(unittest.TestCase):
    def test_valid_rates(self):
        payload = {
            'rates': {
                '2026-03-30': {'IDR': '15000.0'},
                '2026-03-31': {'IDR': '15010.5'},
            }
        }
        mock_resp = Mock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = payload
        mock_resp.raise_for_status = lambda: None

        with patch('requests.get', return_value=mock_resp):
            res = fetch_forex_time_series(
                base='USD',
                symbols=['IDR'],
                start_date='2026-03-30',
                end_date='2026-03-31',
            )
            self.assertIn('rates', res)

    def test_invalid_rates_raises(self):
        payload = {'rates': {'2026-03-30': {'IDR': 'N/A'}}}
        mock_resp = Mock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = payload
        mock_resp.raise_for_status = lambda: None

        with patch('requests.get', return_value=mock_resp):
            with self.assertRaises(RuntimeError):
                fetch_forex_time_series(base='USD', symbols=['IDR'])


if __name__ == '__main__':
    unittest.main()
