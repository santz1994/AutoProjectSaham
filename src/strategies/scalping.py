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

    short_sma = [None] * n
    long_sma = [None] * n

    for i in range(n):
        if i + 1 >= short:
            short_sma[i] = sum(prices[i + 1 - short : i + 1]) / short
        if i + 1 >= long:
            long_sma[i] = sum(prices[i + 1 - long : i + 1]) / long

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
