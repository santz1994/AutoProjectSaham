"""Quick smoke test for ExecutionManager + PaperBrokerAdapter."""
from __future__ import annotations

from src.brokers.paper_adapter import PaperBrokerAdapter
from src.execution.manager import ExecutionManager


def main():
    events = []

    def alert_cb(ev):
        print('ALERT:', ev)
        events.append(ev)

    adapter = PaperBrokerAdapter(starting_cash=10000.0)
    em = ExecutionManager(broker=adapter, max_position_per_symbol=10, daily_loss_limit=0.5, alert_callback=alert_cb)
    em.start_day({'TEST': 100.0})

    # buy 5 shares at 100 -> should fill
    r1 = em.place_order('TEST', 'buy', 5, 100.0, previous_close=100.0)
    print('r1', r1)

    # buy 10 shares -> exceeds position limit (pos would be 15 > 10)
    r2 = em.place_order('TEST', 'buy', 10, 100.0, previous_close=100.0)
    print('r2', r2)

    # sell more than position -> rejected
    r3 = em.place_order('TEST', 'sell', 20, 100.0, previous_close=100.0)
    print('r3', r3)

    print('final balance', em.get_balance({'TEST': 100.0}))


if __name__ == '__main__':
    main()
