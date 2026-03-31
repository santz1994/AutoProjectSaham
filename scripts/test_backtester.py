import json
import os

from src.backtest.vector_backtester import backtest_signals
from src.strategies.scalping import simple_sma_strategy


def main():
    price_file = "data/prices/BBCA.JK.json"
    if not os.path.exists(price_file):
        print("Price file not found:", price_file)
        return

    with open(price_file, "r", encoding="utf-8") as fh:
        payload = json.load(fh)
    prices = payload.get("prices")
    signals = simple_sma_strategy(prices, short=5, long=20)
    res = backtest_signals(prices, signals, initial_cash=10000.0)
    print("Final balance:", res["final_balance"])
    print("Cum return:", res["cum_return"])
    print("Sharpe:", res["sharpe"])
    print("Max drawdown:", res["max_drawdown"])
    print("Trades:", len(res["trades"]))


if __name__ == "__main__":
    main()
