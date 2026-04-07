import os
import sys
import unittest


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


class TradingEnvLiquidityTests(unittest.TestCase):
    def test_zero_volume_buy_is_rejected_with_penalty(self):
        from src.rl.envs.trading_env import TradingEnv

        env = TradingEnv(
            prices=[100.0, 101.0, 102.0],
            volumes=[0.0, 1000.0, 1000.0],
            symbol="TEST",
            starting_cash=10000.0,
            position_size=1,
        )

        reset_result = env.reset()
        if isinstance(reset_result, tuple):
            _obs, _info = reset_result

        step_result = env.step([1, 0])
        if len(step_result) == 5:
            _obs, reward, _terminated, _truncated, info = step_result
        else:
            _obs, reward, _done, info = step_result

        self.assertEqual(info.get("rejected"), "no_liquidity_volume_zero")
        self.assertTrue(info.get("liquidity_penalty"))
        self.assertLessEqual(float(reward), -1.0)
        self.assertEqual(env.manager.broker.positions.get("TEST", 0), 0)

    def test_reward_uses_percent_return_scale(self):
        from src.rl.envs.trading_env import TradingEnv

        env = TradingEnv(
            prices=[100.0, 100.0, 100.0],
            volumes=[1000.0, 1000.0, 1000.0],
            symbol="TEST",
            starting_cash=1_000_000.0,
            position_size=1000,
        )

        reset_result = env.reset()
        if isinstance(reset_result, tuple):
            _obs, _info = reset_result

        step_result = env.step([1, 0])
        if len(step_result) == 5:
            _obs, reward, _terminated, _truncated, info = step_result
        else:
            _obs, reward, _done, info = step_result

        # With high slippage, absolute-Rupiah reward would be around -5000.
        # Percent-based scaling keeps reward in a stable PPO-friendly range.
        self.assertIn("period_return_pct", info)
        self.assertLess(float(reward), 0.0)
        self.assertGreater(float(reward), -10.0)


if __name__ == "__main__":
    unittest.main()
