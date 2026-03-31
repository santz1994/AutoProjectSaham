import unittest
import os
import sys
from unittest.mock import patch, Mock

# ensure src package is importable
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from src.pipeline.data_connectors.news_connector import fetch_news


class NewsConnectorTests(unittest.TestCase):
    def test_valid_articles(self):
        payload = {
            'articles': [
                {
                    'title': 'Test A',
                    'publishedAt': '2026-03-30',
                    'url': 'http://example.com/a',
                },
                {'title': 'Test B', 'publishedAt': '2026-03-31'},
            ],
        }
        mock_resp = Mock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = payload
        mock_resp.raise_for_status = lambda: None

        with patch('requests.get', return_value=mock_resp):
            res = fetch_news('query', api_key='FAKE')
            self.assertIn('articles', res)

    def test_missing_fields_raises(self):
        payload = {'articles': [{'publishedAt': '2026-03-30'}]}
        mock_resp = Mock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = payload
        mock_resp.raise_for_status = lambda: None

        with patch('requests.get', return_value=mock_resp):
            with self.assertRaises(RuntimeError):
                fetch_news('q', api_key='FAKE')


if __name__ == '__main__':
    unittest.main()
