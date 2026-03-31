import os
import sys
import sqlite3
import tempfile
import unittest
from unittest.mock import patch, Mock

# ensure src package is importable
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


class PersistenceTests(unittest.TestCase):
    def test_etl_persistence_creates_db_and_row(self):
        # patch run_etl to avoid external network calls
        with patch(
            'src.pipeline.runner.run_etl',
            return_value={'stocks': {'AAA': []}, 'forex': {}, 'news': {}},
        ):
            mock_fetcher = Mock()
            mock_fetcher.fetch_symbols.return_value = [
                {'symbol': 'AAA', 'status': 'ok'},
            ]

            from src.pipeline.runner import AutonomousPipeline

            with tempfile.TemporaryDirectory() as td:
                db_path = os.path.join(td, 'etl.db')
                runner = AutonomousPipeline(batch_fetcher=mock_fetcher)
                res = runner.run(['AAA'], fetch_prices=True, persist_db=db_path)

                self.assertIn('persisted_run_id', res)
                rid = res['persisted_run_id']
                self.assertIsInstance(rid, int)

                # verify DB row exists
                conn = sqlite3.connect(db_path)
                cur = conn.cursor()
                cur.execute('SELECT COUNT(*) FROM etl_runs')
                cnt = cur.fetchone()[0]
                conn.close()
                self.assertEqual(cnt, 1)


if __name__ == '__main__':
    unittest.main()
