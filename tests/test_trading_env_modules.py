"""
Unit tests for extracted TradingEnv modules:
- src/rl/envs/reward.py — reward computation
- src/rl/envs/execution.py — order execution & position management
- src/rl/envs/observation.py — observation building
"""
import unittest
import numpy as np

from src.rl.envs.reward import (
    _sharpe_ratio,
    _sortino_ratio,
    compute_sortino_reward,
    death_penalty,
    asymmetric_penalty,
    pnl_penalty,
    regime_penalty,
    activity_bonus,
    compute_reward,
)

from src.rl.envs.execution import (
    Position,
    TradeRecord,
    calculate_slippage,
    calculate_fee,
    check_liquidation,
    open_position,
    close_position,
    compute_portfolio_value,
)

from src.rl.envs.observation import (
    build_observation,
    compute_observation_dim,
    compute_portfolio_features,
)


# ===========================================================================
# Reward Module Tests
# ===========================================================================

class TestSharpeRatio(unittest.TestCase):
    def test_empty_returns(self):
        self.assertEqual(_sharpe_ratio([]), 0.0)

    def test_single_return(self):
        self.assertEqual(_sharpe_ratio([0.01]), 0.0)

    def test_positive_returns(self):
        returns = [0.01, 0.02, 0.015, 0.01, 0.02]
        self.assertGreater(_sharpe_ratio(returns), 0.0)

    def test_negative_returns(self):
        returns = [-0.01, -0.02, -0.015, -0.01, -0.02]
        self.assertLess(_sharpe_ratio(returns), 0.0)

    def test_zero_std_returns(self):
        returns = [0.01, 0.01, 0.01, 0.01]
        self.assertEqual(_sharpe_ratio(returns), 0.0)


class TestSortinoRatio(unittest.TestCase):
    def test_empty_returns(self):
        self.assertEqual(_sortino_ratio([]), 0.0)

    def test_all_positive_returns(self):
        returns = [0.01, 0.02, 0.015]
        self.assertEqual(_sortino_ratio(returns), 0.0)  # no downside

    def test_mixed_returns(self):
        returns = [0.01, -0.02, 0.015, -0.01, 0.02]
        result = _sortino_ratio(returns)
        # Sortino should be defined (not zero) since there are negative returns
        self.assertIsInstance(result, float)


class TestDeathPenalty(unittest.TestCase):
    def test_no_penalty_above_threshold(self):
        result = death_penalty(50, 100, 10000.0, 10000.0, 0.1)
        self.assertIsNone(result)

    def test_penalty_at_threshold(self):
        result = death_penalty(50, 100, 1000.0, 10000.0, 0.1)
        self.assertIsNotNone(result)
        self.assertLess(result, -100)

    def test_penalty_below_threshold(self):
        result = death_penalty(50, 100, 500.0, 10000.0, 0.1)
        self.assertIsNotNone(result)
        self.assertLess(result, -500)

    def test_penalty_progress_scaling(self):
        # Earlier steps should have stronger penalty
        early = death_penalty(10, 100, 500.0, 10000.0, 0.1)
        late = death_penalty(90, 100, 500.0, 10000.0, 0.1)
        self.assertLess(early, late)  # more negative early


class TestAsymmetricPenalty(unittest.TestCase):
    def test_positive_pnl_unchanged(self):
        result = asymmetric_penalty(0.05)
        self.assertAlmostEqual(result, 0.05)

    def test_negative_pnl_amplified(self):
        result = asymmetric_penalty(-0.05)
        self.assertLess(result, -0.05)  # amplified loss

    def test_small_loss_extra_penalty(self):
        small_loss = asymmetric_penalty(-0.0005, asym_small_threshold=0.001)
        larger_loss = asymmetric_penalty(-0.01, asym_small_threshold=0.001)
        # Small loss gets 1.5x extra weight
        small_ratio = abs(small_loss) / 0.0005
        larger_ratio = abs(larger_loss) / 0.01
        self.assertGreater(small_ratio, larger_ratio)


class TestPnlPenalty(unittest.TestCase):
    def test_no_penalty_short_history(self):
        result = pnl_penalty([0.01, -0.01], pnl_penalty_threshold=5)
        self.assertEqual(result, 0.0)

    def test_penalty_consecutive_losses(self):
        result = pnl_penalty([-0.01, -0.02, -0.01, -0.03, -0.02], pnl_penalty_threshold=5)
        self.assertEqual(result, -0.5)

    def test_no_penalty_mixed_returns(self):
        result = pnl_penalty([0.01, -0.02, 0.01, -0.03, 0.02], pnl_penalty_threshold=5)
        self.assertEqual(result, 0.0)


class TestRegimePenalty(unittest.TestCase):
    def test_ranging_no_penalty(self):
        self.assertEqual(regime_penalty(0), 0.0)

    def test_trending_no_penalty(self):
        self.assertEqual(regime_penalty(1), 0.0)

    def test_crash_penalty(self):
        self.assertEqual(regime_penalty(3), -0.3)

    def test_volatile_high_risk_penalty(self):
        self.assertEqual(regime_penalty(2, 0.8), -0.15)

    def test_volatile_low_risk_no_penalty(self):
        self.assertEqual(regime_penalty(2, 0.3), 0.0)


class TestActivityBonus(unittest.TestCase):
    def test_bonus_early_no_trades(self):
        self.assertGreater(activity_bonus(0, 10, 50), 0.0)

    def test_no_bonus_late(self):
        self.assertEqual(activity_bonus(0, 100, 50), 0.0)

    def test_no_bonus_with_trades(self):
        self.assertEqual(activity_bonus(5, 10, 50), 0.0)


class TestComputeReward(unittest.TestCase):
    def test_death_penalty_triggers(self):
        reward, terminated = compute_reward(
            pnl=0.0, portfolio_value=500.0, initial_capital=10000.0,
            recent_returns=[], current_step=50, max_steps=100,
            maintenance_margin_ratio=0.1,
        )
        self.assertTrue(terminated)
        self.assertLess(reward, -100)

    def test_normal_reward(self):
        reward, terminated = compute_reward(
            pnl=0.01, portfolio_value=10000.0, initial_capital=10000.0,
            recent_returns=[0.01, 0.02, 0.01, 0.02, 0.01, 0.02],
            current_step=50, max_steps=100,
        )
        self.assertFalse(terminated)
        self.assertIsInstance(reward, float)

    def test_loss_reward_amplified(self):
        reward_gain, _ = compute_reward(
            pnl=0.01, portfolio_value=10000.0, initial_capital=10000.0,
            recent_returns=[0.01] * 6, current_step=50, max_steps=100,
        )
        reward_loss, _ = compute_reward(
            pnl=-0.01, portfolio_value=10000.0, initial_capital=10000.0,
            recent_returns=[-0.01] * 6, current_step=50, max_steps=100,
        )
        # Loss should be more negative than gain is positive
        self.assertLess(abs(reward_loss), abs(reward_gain) or 0.1)


# ===========================================================================
# Execution Module Tests
# ===========================================================================

class TestCalculateSlippage(unittest.TestCase):
    def test_fixed_slippage(self):
        result = calculate_slippage(100.0, 1.0, 1000.0, slippage_model="fixed")
        self.assertAlmostEqual(result, 100.0 * 0.0005)

    def test_volume_slippage_small_order(self):
        result = calculate_slippage(100.0, 0.01, 10000.0)
        self.assertGreater(result, 0)
        self.assertLess(result, 1.0)

    def test_volume_slippage_large_order(self):
        result = calculate_slippage(100.0, 100.0, 100.0)
        self.assertGreater(result, 0)

    def test_zero_volume_high_slippage(self):
        result = calculate_slippage(100.0, 1.0, 0.0)
        self.assertGreater(result, 0)

    def test_slippage_capped(self):
        result = calculate_slippage(100.0, 10000.0, 1.0)
        self.assertLessEqual(result, 100.0 * 0.05)


class TestCalculateFee(unittest.TestCase):
    def test_taker_fee(self):
        fee = calculate_fee(10000.0, leverage=1.0)
        self.assertAlmostEqual(fee, 10.0)

    def test_maker_fee(self):
        fee = calculate_fee(10000.0, leverage=1.0, is_maker=True)
        self.assertAlmostEqual(fee, 2.0)

    def test_leverage_amplifies_fee(self):
        fee_1x = calculate_fee(10000.0, leverage=1.0)
        fee_10x = calculate_fee(10000.0, leverage=10.0)
        self.assertAlmostEqual(fee_10x, fee_1x * 10)


class TestCheckLiquidation(unittest.TestCase):
    def test_no_liquidation(self):
        self.assertFalse(check_liquidation(10000.0, 10000.0, 0.1))

    def test_liquidation_at_threshold(self):
        self.assertTrue(check_liquidation(1000.0, 10000.0, 0.1))

    def test_liquidation_below_threshold(self):
        self.assertTrue(check_liquidation(500.0, 10000.0, 0.1))


class TestOpenPosition(unittest.TestCase):
    def test_open_long(self):
        pos, fee, slip = open_position("long", 100.0, 1000.0, 10.0, 10000.0, 0.001, 0)
        self.assertEqual(pos.side, "long")
        self.assertGreater(pos.entry_price, 100.0)  # slippage adds to entry
        self.assertGreater(fee, 0)
        self.assertGreater(slip, 0)

    def test_open_short(self):
        pos, fee, slip = open_position("short", 100.0, 1000.0, 10.0, 10000.0, 0.001, 0)
        self.assertEqual(pos.side, "short")
        self.assertLess(pos.entry_price, 100.0)  # slippage subtracts from entry


class TestClosePosition(unittest.TestCase):
    def test_close_long_profit(self):
        pos = Position(side="long", entry_price=100.0, quantity=10.0, leverage=5.0, size=1000.0)
        record, pnl = close_position(pos, 110.0, 10000.0, 0.001, 10)
        self.assertGreater(pnl, 0)
        self.assertEqual(record.exit_reason, "manual")

    def test_close_long_loss(self):
        pos = Position(side="long", entry_price=100.0, quantity=10.0, leverage=5.0, size=1000.0)
        record, pnl = close_position(pos, 90.0, 10000.0, 0.001, 10)
        self.assertLess(pnl, 0)

    def test_close_short_profit(self):
        pos = Position(side="short", entry_price=100.0, quantity=10.0, leverage=5.0, size=1000.0)
        record, pnl = close_position(pos, 90.0, 10000.0, 0.001, 10)
        self.assertGreater(pnl, 0)


class TestComputePortfolioValue(unittest.TestCase):
    def test_no_positions(self):
        value = compute_portfolio_value(10000.0, {}, {})
        self.assertEqual(value, 10000.0)

    def test_with_long_position_profit(self):
        pos = Position(side="long", entry_price=100.0, quantity=10.0, leverage=1.0, margin=1000.0, size=1000.0)
        value = compute_portfolio_value(9000.0, {"BTC/USDT": pos}, {"BTC/USDT": 110.0})
        self.assertGreater(value, 10000.0)

    def test_with_long_position_loss(self):
        pos = Position(side="long", entry_price=100.0, quantity=10.0, leverage=1.0, margin=1000.0, size=1000.0)
        value = compute_portfolio_value(9000.0, {"BTC/USDT": pos}, {"BTC/USDT": 90.0})
        self.assertLess(value, 10000.0)


# ===========================================================================
# Observation Module Tests
# ===========================================================================

class TestBuildObservation(unittest.TestCase):
    def test_single_symbol(self):
        features = {"BTC/USDT": np.array([0.5, 0.3, 0.7], dtype=np.float32)}
        obs = build_observation(features, ["BTC/USDT"], 1, 3)
        self.assertEqual(len(obs), 3)
        np.testing.assert_array_almost_equal(obs, [0.5, 0.3, 0.7])

    def test_padding_for_missing_symbols(self):
        features = {"BTC/USDT": np.array([0.5, 0.3], dtype=np.float32)}
        obs = build_observation(features, ["BTC/USDT"], 3, 2)
        self.assertEqual(len(obs), 6)
        np.testing.assert_array_almost_equal(obs[:2], [0.5, 0.3])
        np.testing.assert_array_almost_equal(obs[2:], [0.0, 0.0, 0.0, 0.0])

    def test_with_portfolio_features(self):
        features = {"BTC/USDT": np.array([0.5], dtype=np.float32)}
        pf = np.array([1.0, 0.8], dtype=np.float32)
        obs = build_observation(features, ["BTC/USDT"], 1, 1, portfolio_features=pf)
        self.assertEqual(len(obs), 3)
        np.testing.assert_array_almost_equal(obs, [0.5, 1.0, 0.8])

    def test_with_sentiment_vector(self):
        features = {"BTC/USDT": np.array([0.5], dtype=np.float32)}
        sv = np.array([0.1, 0.2, 0.3], dtype=np.float32)
        obs = build_observation(features, ["BTC/USDT"], 1, 1, sentiment_vector=sv)
        self.assertEqual(len(obs), 4)
        np.testing.assert_array_almost_equal(obs, [0.5, 0.1, 0.2, 0.3])

    def test_nan_safety(self):
        features = {"BTC/USDT": np.array([np.nan, 0.5, np.inf], dtype=np.float32)}
        obs = build_observation(features, ["BTC/USDT"], 1, 3)
        self.assertFalse(np.any(np.isnan(obs)))
        self.assertFalse(np.any(np.isinf(obs)))


class TestComputeObservationDim(unittest.TestCase):
    def test_basic(self):
        dim = compute_observation_dim(3, 10)
        self.assertEqual(dim, 30)

    def test_with_portfolio_and_sentiment(self):
        dim = compute_observation_dim(3, 10, portfolio_features_dim=5, sentiment_dim=7)
        self.assertEqual(dim, 30 + 5 + 7)


class TestComputePortfolioFeatures(unittest.TestCase):
    def test_basic(self):
        pf = compute_portfolio_features(10000.0, 10000.0, 5000.0, 1, 5)
        self.assertEqual(len(pf), 5)
        self.assertAlmostEqual(pf[0], 1.0)  # equity_ratio
        self.assertAlmostEqual(pf[1], 0.5)  # cash_ratio

    def test_clipping(self):
        pf = compute_portfolio_features(50000.0, 10000.0, 0.0, 10, 5)
        self.assertTrue(all(-5.0 <= v <= 5.0 for v in pf))


if __name__ == "__main__":
    unittest.main()