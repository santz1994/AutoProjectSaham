import os
import sys
import unittest

# ensure src package is importable when tests run directly
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from src.brokers.retry_wrapper import RetryBrokerAdapter


class FlakyAdapter:
    """A minimal adapter that fails a configurable number of times before succeeding."""
    def __init__(self, place_fail_times: int = 0, connect_fail_times: int = 0):
        self.place_calls = 0
        self.connect_calls = 0
        self.place_fail_times = int(place_fail_times)
        self.connect_fail_times = int(connect_fail_times)
        self.positions = {}
        self.cash = 10000.0

    def connect(self):
        self.connect_calls += 1
        if self.connect_calls <= self.connect_fail_times:
            raise RuntimeError('connect temporary error')
        return True

    def place_order(self, symbol, side, qty, price):
        self.place_calls += 1
        if self.place_calls <= self.place_fail_times:
            raise RuntimeError('temporary place failure')
        # simple deterministic fill
        if side.lower() == 'buy':
            self.positions[symbol] = self.positions.get(symbol, 0) + int(qty)
            self.cash -= float(price) * int(qty)
            return {'status': 'filled'}
        return {'status': 'rejected'}

    def cancel_order(self, order_id):
        return False

    def get_positions(self):
        return dict(self.positions)

    def get_cash(self):
        return float(self.cash)

    def get_balance(self, price_map=None):
        total = float(self.cash)
        if price_map:
            for s, q in self.positions.items():
                total += price_map.get(s, 0.0) * q
        return total

    def disconnect(self):
        return None

    def reconcile(self):
        return {
            'positions': self.get_positions(),
            'cash': self.get_cash(),
            'balance': self.get_balance({}),
        }


class RetryWrapperTests(unittest.TestCase):
    def test_place_order_succeeds_after_retries(self):
        flaky = FlakyAdapter(place_fail_times=2)
        wrapper = RetryBrokerAdapter(
            flaky,
            max_retries=3,
            initial_backoff=0.001,
            max_backoff=0.005,
            jitter=0.0,
        )
        res = wrapper.place_order('X', 'buy', 1, 10.0)
        self.assertEqual(res.get('status'), 'filled')

    def test_place_order_exceeds_retries(self):
        flaky = FlakyAdapter(place_fail_times=5)
        wrapper = RetryBrokerAdapter(
            flaky,
            max_retries=3,
            initial_backoff=0.001,
            max_backoff=0.005,
            jitter=0.0,
        )
        with self.assertRaises(RuntimeError):
            wrapper.place_order('X', 'buy', 1, 10.0)

    def test_connect_retries(self):
        flaky = FlakyAdapter(connect_fail_times=2)
        wrapper = RetryBrokerAdapter(
            flaky,
            max_retries=3,
            initial_backoff=0.001,
            max_backoff=0.005,
            jitter=0.0,
        )
        self.assertTrue(wrapper.connect())


if __name__ == '__main__':
    unittest.main()
