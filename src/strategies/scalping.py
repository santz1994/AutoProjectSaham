"""Simple strategy implementations.

The functions here use plain Python so they can be demo-run without heavy deps.
"""

from typing import List


def simple_sma_strategy(prices: List[float], short: int = 5, long: int = 20):
    """Generate basic SMA crossover signals.

    Returns a list of integers equal to len(prices):
      1  -> buy signal
     -1  -> sell signal
      0  -> hold / no action

    This is intentionally simple for demo and backtesting.
    """
    n = len(prices)
    if n == 0:
        return []
    if short <= 0 or long <= 0:
        raise ValueError("short and long windows must be > 0")

    short_sma = [None] * n
    long_sma = [None] * n

    short_sum = 0.0
    long_sum = 0.0

    for i in range(n):
        price = float(prices[i])
        short_sum += price
        long_sum += price

        if i >= short:
            short_sum -= float(prices[i - short])
        if i >= long:
            long_sum -= float(prices[i - long])

        if i + 1 >= short:
            short_sma[i] = short_sum / short
        if i + 1 >= long:
            long_sma[i] = long_sum / long

    signals = [0] * n
    for i in range(1, n):
        if short_sma[i] is None or long_sma[i] is None:
            continue
        prev_s = short_sma[i - 1]
        prev_l = long_sma[i - 1]
        cur_s = short_sma[i]
        cur_l = long_sma[i]
        if prev_s is None or prev_l is None:
            continue

        # Bullish crossover
        if cur_s > cur_l and prev_s <= prev_l:
            signals[i] = 1
        # Bearish crossover
        elif cur_s < cur_l and prev_s >= prev_l:
            signals[i] = -1

    return signals
