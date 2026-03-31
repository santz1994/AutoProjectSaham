import os
import sys
import unittest

# ensure src package is importable
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


class BacktesterTests(unittest.TestCase):
    def test_eod_execution_and_slippage(self):
        from src.backtest.backtester import simple_backtest

        prices = [100.0, 105.0, 110.0]
        # signal at day 0 -> buy at day 1 (105); signal at day1 -> sell at day2 (110)
        signals = [1, -1, 0]
        res = simple_backtest(
            prices,
            signals,
            starting_cash=20000.0,
            lot_size=100,
            slippage_pct=0.0,
            buy_fee_pct=0.0,
            sell_fee_pct=0.0,
        )
        trades = res["trades"]
        # Expect two trades: buy at index 1 and sell at index 2
        self.assertEqual(len(trades), 2)
        self.assertEqual(trades[0][0], "buy")
        self.assertEqual(trades[0][1], 1)
        self.assertEqual(trades[1][0], "sell")
        self.assertEqual(trades[1][1], 2)
        # final balance should reflect buy at 105 and sell at 110 (profit 500)
        self.assertAlmostEqual(res["final_balance"], 20500.0)

    def test_slippage_reduces_profit(self):
        from src.backtest.backtester import simple_backtest

        prices = [100.0, 105.0, 110.0]
        signals = [1, -1, 0]
        res_no_slip = simple_backtest(
            prices,
            signals,
            starting_cash=20000.0,
            lot_size=100,
            slippage_pct=0.0,
            buy_fee_pct=0.0,
            sell_fee_pct=0.0,
        )
        res_slip = simple_backtest(
            prices,
            signals,
            starting_cash=20000.0,
            lot_size=100,
            slippage_pct=0.01,
            buy_fee_pct=0.0,
            sell_fee_pct=0.0,
        )
        self.assertLess(res_slip["final_balance"], res_no_slip["final_balance"])


if __name__ == "__main__":
    unittest.main()
