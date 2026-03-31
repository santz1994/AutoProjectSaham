import unittest
import os
import sys

# ensure src package is importable
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from src.brokers.paper_adapter import PaperBrokerAdapter


class BrokerAdapterTests(unittest.TestCase):
    def test_reconcile_snapshot(self):
        adapter = PaperBrokerAdapter(starting_cash=10000.0)
        adapter.connect()

        # buy 5 shares at 100
        r = adapter.place_order('TEST', 'buy', 5, 100.0)
        self.assertEqual(r.get('status'), 'filled')

        snap = adapter.reconcile()
        self.assertIn('positions', snap)
        self.assertIn('cash', snap)
        self.assertEqual(snap['positions'].get('TEST', 0), 5)

        # expected cash after buy = 10000 - (5*100) - fee(0.15%)
        expected_cash = 10000.0 - (5 * 100.0) - (5 * 100.0 * 0.0015)
        self.assertAlmostEqual(snap['cash'], expected_cash, places=6)

    def test_reconcile_with_expected(self):
        adapter = PaperBrokerAdapter(starting_cash=5000.0)
        adapter.connect()
        adapter.place_order('AAA', 'buy', 10, 10.0)
        report = adapter.reconcile_with_expected({'AAA': 10}, expected_cash=None)
        self.assertTrue(report.get('ok'))


if __name__ == '__main__':
    unittest.main()
