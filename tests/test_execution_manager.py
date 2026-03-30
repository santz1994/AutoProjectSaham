import os
import sys
import unittest

# ensure src package is importable when tests run directly
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from src.brokers.paper_adapter import PaperBrokerAdapter
from src.execution.manager import ExecutionManager


class ExecutionManagerTests(unittest.TestCase):
    def test_buy_fill_and_reject_limits(self):
        events = []

        def cb(ev):
            events.append(ev)

        adapter = PaperBrokerAdapter(starting_cash=10000.0)
        em = ExecutionManager(broker=adapter, max_position_per_symbol=10, daily_loss_limit=0.5, alert_callback=cb)
        em.start_day({'TEST': 100.0})

        r1 = em.place_order('TEST', 'buy', 5, 100.0, previous_close=100.0)
        self.assertEqual(r1.get('status'), 'filled')

        r2 = em.place_order('TEST', 'buy', 10, 100.0, previous_close=100.0)
        self.assertEqual(r2.get('status'), 'rejected')

        # ensure callback recorded events (at least rejects)
        self.assertTrue(any(ev.get('type') == 'order_rejected' for ev in events))


if __name__ == '__main__':
    unittest.main()
