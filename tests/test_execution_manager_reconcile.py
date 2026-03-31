import os
import sys
import time
import unittest

# ensure src package is importable when tests run directly
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from src.brokers.paper_adapter import PaperBrokerAdapter
from src.execution.manager import ExecutionManager


class ExecutionManagerReconcileTests(unittest.TestCase):
    def test_detects_external_drift(self):
        events = []

        def cb(ev):
            events.append(ev)

        adapter = PaperBrokerAdapter(starting_cash=10000.0)
        em = ExecutionManager(broker=adapter, alert_callback=cb)
        em.start_day({'FOO': 100.0})

        # external action performed directly on adapter (out-of-band)
        adapter.place_order('FOO', 'buy', 5, 100.0)

        # reconciliation should detect the manager's expected state differs
        report = em.reconcile_once(alert_on_drift=True)
        self.assertFalse(report.get('ok'))
        self.assertTrue(any(ev.get('type') == 'reconcile_drift' for ev in events))

    def test_start_stop_loop(self):
        adapter = PaperBrokerAdapter(starting_cash=10000.0)
        em = ExecutionManager(broker=adapter)
        em.start_day({'FOO': 100.0})
        started = em.start_reconciliation_loop(
            interval_seconds=0.1,
            alert_on_drift=False,
        )
        self.assertTrue(started)
        time.sleep(0.25)
        em.stop_reconciliation_loop()


if __name__ == '__main__':
    unittest.main()
