"""Lightweight demo runner using pure-Python components.

This demo avoids external packages so it can run out-of-the-box.
"""
import random

from .execution.executor import PaperBroker
from .strategies.scalping import simple_sma_strategy


def generate_price_series(n=200, start_price=100.0, volatility_pct=1.0):
    p = float(start_price)
    prices = []
    for _ in range(n):
        change = random.uniform(-volatility_pct, volatility_pct)
        p = max(0.01, p * (1 + change / 100.0))
        prices.append(round(p, 4))
    return prices


def run_demo():
    print("Starting AutoSaham demo — generating simulated prices...")
    prices = generate_price_series(n=200, start_price=100.0, volatility_pct=1.5)
    signals = simple_sma_strategy(prices, short=5, long=20)

    broker = PaperBroker(cash=10000.0)
    symbol = "DEMO"

    for t, price in enumerate(prices):
        action = signals[t]
        if action == 1:
            # buy one unit
            broker.place_order(symbol, "buy", 1, price)
        elif action == -1:
            # sell all holdings
            qty = broker.positions.get(symbol, 0)
            if qty > 0:
                broker.place_order(symbol, "sell", qty, price)

    final_bal = broker.get_balance({symbol: prices[-1]})
    print("Demo complete — final balance (cash + market value):", round(final_bal, 2))
    print("Trades executed:", len(broker.trades))
    for t in broker.trades[:10]:
        print(t)
