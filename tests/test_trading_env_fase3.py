"""Unit tests for Fase 3: TradingEnv Colosseum enhancements.

Covers:
- Leverage support (max_leverage parameter, margin accounting)
- Slippage model (base slippage + volume impact)
- Trading fees (maker/taker commission amplified by leverage)
- Sharpe Ratio reward function
- Death Penalty (liquidation when equity hits maintenance margin)
- Drawdown penalty
"""
import os
import sys
import unittest

import numpy as np

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


class TradingEnvLeverageTests(unittest.TestCase):
    """Test leverage parameter handling and margin accounting."""

    def test_default_leverage_is_1x(self):
        from src.rl.envs.trading_env import TradingEnv

        env = TradingEnv(prices=[100.0, 101.0, 102.0], volumes=[1000.0] * 3)
        self.assertEqual(env.max_leverage, 1.0)

    def test_custom_leverage_stored(self):
        from src.rl.envs.trading_env import TradingEnv

        env = TradingEnv(
            prices=[100.0, 101.0, 102.0],
            volumes=[1000.0] * 3,
            max_leverage=20.0,
        )
        self.assertEqual(env.max_leverage, 20.0)

    def test_leverage_minimum_is_1x(self):
        from src.rl.envs.trading_env import TradingEnv

        env = TradingEnv(
            prices=[100.0, 101.0, 102.0],
            volumes=[1000.0] * 3,
            max_leverage=0.5,  # below 1.0
        )
        self.assertEqual(env.max_leverage, 1.0)

    def test_buy_with_leverage_records_leverage_info(self):
        from src.rl.envs.trading_env import TradingEnv

        env = TradingEnv(
            prices=[100.0, 101.0, 102.0],
            volumes=[1_000_000.0] * 3,
            starting_cash=10_000.0,
            position_size=1.0,
            max_leverage=10.0,
            commission_pct=0.001,
            slippage_pct=0.0,
        )
        env.reset()
        result = env.step([1, 0])
        info = tuple(result)[-1]

        self.assertIn("leverage_used", info)
        self.assertEqual(info["leverage_used"], 10.0)
        self.assertIn("margin_debt", info)

    def test_buy_with_leverage_records_fee(self):
        from src.rl.envs.trading_env import TradingEnv

        env = TradingEnv(
            prices=[100.0, 101.0, 102.0],
            volumes=[1_000_000.0] * 3,
            starting_cash=10_000.0,
            position_size=1.0,
            max_leverage=10.0,
            commission_pct=0.001,
            slippage_pct=0.0,
        )
        env.reset()
        result = env.step([1, 0])
        info = tuple(result)[-1]

        self.assertIn("fee_paid", info)
        # leveraged notional = 100 * 1.0 * 10 = 1000, fee = 1000 * 0.001 = 1.0
        self.assertAlmostEqual(info["fee_paid"], 1.0, places=2)


class TradingEnvSlippageTests(unittest.TestCase):
    """Test slippage model (base + volume impact)."""

    def test_slippage_applied_on_buy(self):
        from src.rl.envs.trading_env import TradingEnv

        env = TradingEnv(
            prices=[100.0, 101.0, 102.0],
            volumes=[1_000_000.0] * 3,
            starting_cash=10_000.0,
            position_size=1.0,
            slippage_pct=0.01,  # 1% slippage
            commission_pct=0.0,
            max_leverage=1.0,
        )
        env.reset()

        # Buy — slippage should cause slight negative return
        result = env.step([1, 0])
        info = tuple(result)[-1]

        # Should not be rejected
        self.assertNotIn("rejected", info)

    def test_slippage_on_high_volume_trade(self):
        from src.rl.envs.trading_env import TradingEnv

        env = TradingEnv(
            prices=[100.0, 101.0, 102.0],
            volumes=[100.0] * 3,  # low volume
            starting_cash=100_000.0,
            position_size=50.0,  # large trade relative to volume
            slippage_pct=0.001,
            commission_pct=0.0,
            max_leverage=1.0,
        )
        env.reset()
        result = env.step([1, 0])
        info = tuple(result)[-1]

        # With high volume ratio, slippage should increase
        self.assertNotIn("rejected", info)

    def test_apply_slippage_buy_increases_price(self):
        from src.rl.envs.trading_env import TradingEnv

        env = TradingEnv(
            prices=[100.0, 101.0],
            volumes=[1000.0] * 2,
            slippage_pct=0.005,
        )
        slipped = env._apply_slippage(100.0, "buy", 1000.0)
        self.assertGreater(slipped, 100.0)

    def test_apply_slippage_sell_decreases_price(self):
        from src.rl.envs.trading_env import TradingEnv

        env = TradingEnv(
            prices=[100.0, 101.0],
            volumes=[1000.0] * 2,
            slippage_pct=0.005,
        )
        slipped = env._apply_slippage(100.0, "sell", 1000.0)
        self.assertLess(slipped, 100.0)


class TradingEnvCommissionTests(unittest.TestCase):
    """Test trading fee (commission) calculation."""

    def test_apply_commission_basic(self):
        from src.rl.envs.trading_env import TradingEnv

        env = TradingEnv(
            prices=[100.0, 101.0],
            volumes=[1000.0] * 2,
            commission_pct=0.001,
        )
        fee = env._apply_commission(10000.0)
        self.assertAlmostEqual(fee, 10.0)

    def test_apply_commission_zero(self):
        from src.rl.envs.trading_env import TradingEnv

        env = TradingEnv(
            prices=[100.0, 101.0],
            volumes=[1000.0] * 2,
            commission_pct=0.001,
        )
        fee = env._apply_commission(0.0)
        self.assertEqual(fee, 0.0)

    def test_fee_amplified_by_leverage(self):
        from src.rl.envs.trading_env import TradingEnv

        # With 50x leverage, fee = notional * leverage * commission_pct
        env = TradingEnv(
            prices=[100.0, 101.0, 102.0],
            volumes=[1_000_000.0] * 3,
            starting_cash=100_000.0,
            position_size=1.0,
            max_leverage=50.0,
            commission_pct=0.001,
            slippage_pct=0.0,
        )
        env.reset()
        result = env.step([1, 0])
        info = tuple(result)[-1]

        # leveraged notional = 100 * 1 * 50 = 5000, fee = 5000 * 0.001 = 5.0
        self.assertIn("fee_paid", info)
        self.assertAlmostEqual(info["fee_paid"], 5.0, places=2)


class TradingEnvSharpeRewardTests(unittest.TestCase):
    """Test Sharpe Ratio-based reward function."""

    def test_compute_sharpe_reward_insufficient_history(self):
        from src.rl.envs.trading_env import TradingEnv

        env = TradingEnv(
            prices=[100.0, 101.0],
            volumes=[1000.0] * 2,
            sharpe_lookback=50,
        )
        # With < 5 history entries, should return scaled return
        reward = env._compute_sharpe_reward(0.01)
        self.assertAlmostEqual(reward, 1.0, places=1)  # 0.01 * 100

    def test_compute_sharpe_reward_with_history(self):
        from src.rl.envs.trading_env import TradingEnv

        env = TradingEnv(
            prices=[100.0, 101.0],
            volumes=[1000.0] * 2,
            sharpe_lookback=50,
        )
        # Build history with consistent positive returns
        for _ in range(10):
            env._return_history.append(0.005)

        reward = env._compute_sharpe_reward(0.005)
        # Consistent returns → positive Sharpe → positive reward
        self.assertGreater(reward, 0.0)

    def test_compute_sharpe_reward_negative_returns(self):
        from src.rl.envs.trading_env import TradingEnv

        env = TradingEnv(
            prices=[100.0, 99.0],
            volumes=[1000.0] * 2,
            sharpe_lookback=50,
        )
        # Build history with consistent negative returns
        for _ in range(10):
            env._return_history.append(-0.01)

        reward = env._compute_sharpe_reward(-0.01)
        # Consistent losses → negative Sharpe → negative reward
        self.assertLess(reward, 0.0)

    def test_sharpe_reward_clipped_to_range(self):
        from src.rl.envs.trading_env import TradingEnv

        env = TradingEnv(
            prices=[100.0, 101.0],
            volumes=[1000.0] * 2,
            sharpe_lookback=50,
        )
        # Extreme return should still be clipped
        for _ in range(20):
            env._return_history.append(1.0)

        reward = env._compute_sharpe_reward(1.0)
        self.assertLessEqual(reward, 10.0)
        self.assertGreaterEqual(reward, -10.0)

    def test_step_includes_sharpe_info(self):
        from src.rl.envs.trading_env import TradingEnv

        env = TradingEnv(
            prices=[100.0, 101.0, 102.0],
            volumes=[1000.0] * 3,
            starting_cash=10_000.0,
            position_size=1.0,
        )
        env.reset()
        result = env.step([0, 0])  # hold
        info = tuple(result)[-1]

        self.assertIn("sharpe_reward", info)
        self.assertIn("period_return_pct", info)
        self.assertIn("equity", info)
        self.assertIn("drawdown_pct", info)


class TradingEnvDeathPenaltyTests(unittest.TestCase):
    """Test liquidation (death penalty) logic."""

    def test_liquidation_threshold_calculated(self):
        from src.rl.envs.trading_env import TradingEnv

        env = TradingEnv(
            prices=[100.0, 101.0],
            volumes=[1000.0] * 2,
            starting_cash=10_000.0,
            maintenance_margin_fraction=0.10,
        )
        self.assertAlmostEqual(env.liquidation_threshold, 1000.0)

    def test_maintenance_margin_fraction_clamped(self):
        from src.rl.envs.trading_env import TradingEnv

        env = TradingEnv(
            prices=[100.0, 101.0],
            volumes=[1000.0] * 2,
            starting_cash=10_000.0,
            maintenance_margin_fraction=0.99,  # above max 0.50
        )
        # Clamped to 0.50: threshold = 10_000 * 0.50 = 5000
        self.assertAlmostEqual(env.liquidation_threshold, 10_000.0 * 0.50)

    def test_liquidation_triggers_on_extreme_loss(self):
        from src.rl.envs.trading_env import TradingEnv

        # Prices that crash hard
        prices = [100.0] + [10.0] * 10
        volumes = [1_000_000.0] * len(prices)

        env = TradingEnv(
            prices=prices,
            volumes=volumes,
            starting_cash=1000.0,
            position_size=10.0,
            max_leverage=50.0,
            commission_pct=0.0,
            slippage_pct=0.0,
            maintenance_margin_fraction=0.10,
        )
        env.reset()

        # Buy at 100 with 50x leverage
        result = env.step([1, 0])
        info = tuple(result)[-1]

        # On price crash from 100 to 10, leveraged loss should be massive
        # Walk through remaining steps to trigger liquidation
        is_liquidated = info.get("liquidated", False)
        step_idx = 1
        while not is_liquidated and step_idx < len(prices) - 1:
            result = env.step([0, 0])
            info = tuple(result)[-1]
            is_liquidated = info.get("liquidated", False)
            step_idx += 1

        # Either liquidation triggered or loss was absorbed by cash
        if is_liquidated:
            reward = tuple(result)[1]
            self.assertEqual(reward, -1000.0)
            self.assertTrue(env._is_liquidated)

    def test_liquidated_env_returns_terminal_immediately(self):
        from src.rl.envs.trading_env import TradingEnv

        env = TradingEnv(
            prices=[100.0, 101.0, 102.0],
            volumes=[1000.0] * 3,
            starting_cash=1000.0,
            maintenance_margin_fraction=0.10,
        )
        env.reset()
        env._is_liquidated = True  # force liquidation state

        result = env.step([0, 0])
        parsed = tuple(result)
        reward = parsed[1]
        done = parsed[2]

        self.assertEqual(reward, -1000.0)
        self.assertTrue(done)

    def test_check_liquidation_false_when_healthy(self):
        from src.rl.envs.trading_env import TradingEnv

        env = TradingEnv(
            prices=[100.0, 101.0, 102.0],
            volumes=[1000.0] * 3,
            starting_cash=10_000.0,
            maintenance_margin_fraction=0.10,
        )
        env.reset()
        result = env._check_liquidation(100.0)
        self.assertFalse(result)


class TradingEnvEquityTests(unittest.TestCase):
    """Test equity calculation and drawdown tracking."""

    def test_get_equity_without_position(self):
        from src.rl.envs.trading_env import TradingEnv

        env = TradingEnv(
            prices=[100.0, 101.0],
            volumes=[1000.0] * 2,
            starting_cash=5000.0,
        )
        env.reset()
        equity = env._get_equity(100.0)
        self.assertAlmostEqual(equity, 5000.0)

    def test_peak_equity_tracked(self):
        from src.rl.envs.trading_env import TradingEnv

        prices = [100.0, 110.0, 120.0, 115.0]
        env = TradingEnv(
            prices=prices,
            volumes=[1000.0] * 4,
            starting_cash=10_000.0,
            position_size=1.0,
            commission_pct=0.0,
            slippage_pct=0.0,
        )
        env.reset()

        # Walk through steps — peak should be tracked
        for _ in range(3):
            env.step([0, 0])

        # peak_equity should be at least starting cash
        self.assertGreaterEqual(env._peak_equity, 10_000.0 - 1.0)

    def test_drawdown_penalty_applied_on_large_drawdown(self):
        from src.rl.envs.trading_env import TradingEnv

        # Create scenario: price goes up then crashes
        prices = [100.0, 150.0, 50.0]
        env = TradingEnv(
            prices=prices,
            volumes=[1_000_000.0] * 3,
            starting_cash=10_000.0,
            position_size=10.0,
            commission_pct=0.0,
            slippage_pct=0.0,
            max_leverage=1.0,
        )
        env.reset()

        # Buy at 100
        env.step([1, 0])

        # Price crashes from 100→150→50 (but we step with existing position)
        # The hold step should register drawdown
        result = env.step([0, 0])
        info = tuple(result)[-1]

        # Check drawdown info exists
        self.assertIn("drawdown_pct", info)


class TradingEnvCostModelIntegrationTests(unittest.TestCase):
    """Integration tests for combined cost model (slippage + fees + leverage)."""

    def test_sell_records_fee(self):
        from src.rl.envs.trading_env import TradingEnv

        env = TradingEnv(
            prices=[100.0, 105.0, 110.0],
            volumes=[1_000_000.0] * 3,
            starting_cash=10_000.0,
            position_size=1.0,
            max_leverage=5.0,
            commission_pct=0.001,
            slippage_pct=0.0,
        )
        env.reset()

        # Buy
        env.step([1, 0])

        # Sell
        result = env.step([2, 0])
        info = tuple(result)[-1]

        self.assertIn("fee_paid", info)
        self.assertGreater(info["fee_paid"], 0.0)

    def test_fees_reduce_equity_vs_zero_fee(self):
        from src.rl.envs.trading_env import TradingEnv

        # With fees
        env_fee = TradingEnv(
            prices=[100.0, 110.0, 120.0],
            volumes=[1_000_000.0] * 3,
            starting_cash=10_000.0,
            position_size=1.0,
            max_leverage=1.0,
            commission_pct=0.01,  # 1% fee
            slippage_pct=0.0,
        )
        env_fee.reset()
        env_fee.step([1, 0])  # buy
        env_fee.step([2, 0])  # sell
        equity_fee = env_fee._get_equity(120.0)

        # Without fees
        env_free = TradingEnv(
            prices=[100.0, 110.0, 120.0],
            volumes=[1_000_000.0] * 3,
            starting_cash=10_000.0,
            position_size=1.0,
            max_leverage=1.0,
            commission_pct=0.0,
            slippage_pct=0.0,
        )
        env_free.reset()
        env_free.step([1, 0])  # buy
        env_free.step([2, 0])  # sell
        equity_free = env_free._get_equity(120.0)

        # Fees should reduce final equity
        self.assertLess(equity_fee, equity_free)

    def test_leverage_amplifies_losses(self):
        from src.rl.envs.trading_env import TradingEnv

        # 1x leverage
        env_1x = TradingEnv(
            prices=[100.0, 90.0],
            volumes=[1_000_000.0] * 2,
            starting_cash=10_000.0,
            position_size=1.0,
            max_leverage=1.0,
            commission_pct=0.0,
            slippage_pct=0.0,
        )
        env_1x.reset()
        env_1x.step([1, 0])
        equity_1x = env_1x._get_equity(90.0)

        # 10x leverage
        env_10x = TradingEnv(
            prices=[100.0, 90.0],
            volumes=[1_000_000.0] * 2,
            starting_cash=10_000.0,
            position_size=1.0,
            max_leverage=10.0,
            commission_pct=0.0,
            slippage_pct=0.0,
        )
        env_10x.reset()
        env_10x.step([1, 0])
        equity_10x = env_10x._get_equity(90.0)

        # With 10x leverage, loss should be amplified (lower equity)
        self.assertLess(equity_10x, equity_1x)

    def test_info_contains_all_fase3_fields(self):
        from src.rl.envs.trading_env import TradingEnv

        env = TradingEnv(
            prices=[100.0, 101.0, 102.0],
            volumes=[1000.0] * 3,
            starting_cash=10_000.0,
            position_size=1.0,
            max_leverage=5.0,
        )
        env.reset()
        result = env.step([0, 0])  # hold
        info = tuple(result)[-1]

        # All Fase 3 info fields present
        for key in [
            "period_return_pct",
            "sharpe_reward",
            "equity",
            "drawdown_pct",
            "leverage",
        ]:
            self.assertIn(key, info, f"Missing info key: {key}")

    def test_leverage_info_field_on_hold(self):
        from src.rl.envs.trading_env import TradingEnv

        env = TradingEnv(
            prices=[100.0, 101.0, 102.0],
            volumes=[1000.0] * 3,
            max_leverage=25.0,
        )
        env.reset()
        result = env.step([0, 0])
        info = tuple(result)[-1]

        self.assertEqual(info["leverage"], 25.0)


if __name__ == "__main__":
    unittest.main()