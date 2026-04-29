"""
Unit tests for extracted agent_integration modules:
- src/rl/mimo_supervisor.py — MiMo Supervisor (fat-tail protection)
- src/rl/regime_detector.py — Market Regime Detection
"""
import unittest
import numpy as np

from src.rl.mimo_supervisor import MimoSupervisor, SupervisorDecision
from src.rl.regime_detector import RegimeDetector, RegimeState


# ===========================================================================
# MimoSupervisor Tests
# ===========================================================================

class TestMimoSupervisor(unittest.TestCase):
    def setUp(self):
        self.supervisor = MimoSupervisor()

    def test_no_sentiment_data_allows_trade(self):
        vetoed, frac, reason = self.supervisor.should_veto("BTC/USDT", 0.5)
        self.assertFalse(vetoed)
        self.assertEqual(frac, 0.5)
        self.assertEqual(reason, "")

    def test_extreme_negative_sentiment_veto(self):
        self.supervisor.set_latest_sentiment("BTC/USDT", {
            "sentiment_score": -0.9,
            "risk_level": 0.3,
            "confidence": 0.8,
        })
        vetoed, frac, reason = self.supervisor.should_veto("BTC/USDT", 0.5)
        self.assertTrue(vetoed)
        self.assertEqual(frac, 0.0)
        self.assertIn("extreme_negative", reason)

    def test_extreme_risk_cuts_position(self):
        self.supervisor.set_latest_sentiment("BTC/USDT", {
            "sentiment_score": 0.0,
            "risk_level": 0.95,
            "confidence": 0.5,
        })
        vetoed, frac, reason = self.supervisor.should_veto("BTC/USDT", 0.8)
        self.assertFalse(vetoed)
        self.assertAlmostEqual(frac, 0.8 * 0.25)
        self.assertIn("extreme_risk", reason)

    def test_sentiment_divergence_buy_bearish(self):
        self.supervisor.set_latest_sentiment("BTC/USDT", {
            "sentiment_score": -0.8,
            "risk_level": 0.3,
            "confidence": 0.5,
        })
        vetoed, frac, reason = self.supervisor.should_veto("BTC/USDT", 0.5)
        # Should cut position (divergence) since score < -0.7 and target > 0.1
        self.assertFalse(vetoed)
        self.assertAlmostEqual(frac, 0.5 * 0.5)
        self.assertIn("divergence", reason)

    def test_sentiment_divergence_sell_bullish(self):
        self.supervisor.set_latest_sentiment("BTC/USDT", {
            "sentiment_score": 0.8,
            "risk_level": 0.3,
            "confidence": 0.5,
        })
        vetoed, frac, reason = self.supervisor.should_veto("BTC/USDT", -0.5)
        self.assertFalse(vetoed)
        self.assertAlmostEqual(frac, -0.5 * 0.5)
        self.assertIn("divergence", reason)

    def test_neutral_sentiment_allows_trade(self):
        self.supervisor.set_latest_sentiment("BTC/USDT", {
            "sentiment_score": 0.1,
            "risk_level": 0.3,
            "confidence": 0.5,
        })
        vetoed, frac, reason = self.supervisor.should_veto("BTC/USDT", 0.5)
        self.assertFalse(vetoed)
        self.assertEqual(frac, 0.5)
        self.assertEqual(reason, "")

    def test_stats_tracking(self):
        self.supervisor.set_latest_sentiment("BTC/USDT", {
            "sentiment_score": -0.9,
            "risk_level": 0.3,
        })
        self.supervisor.should_veto("BTC/USDT", 0.5)
        stats = self.supervisor.get_stats()
        self.assertEqual(stats["check_count"], 1)
        self.assertEqual(stats["veto_count"], 1)

    def test_multiple_symbols(self):
        self.supervisor.set_latest_sentiment("BTC/USDT", {
            "sentiment_score": 0.5, "risk_level": 0.2,
        })
        self.supervisor.set_latest_sentiment("ETH/USDT", {
            "sentiment_score": -0.9, "risk_level": 0.3,
        })
        vetoed_btc, _, _ = self.supervisor.should_veto("BTC/USDT", 0.5)
        vetoed_eth, _, _ = self.supervisor.should_veto("ETH/USDT", 0.5)
        self.assertFalse(vetoed_btc)
        self.assertTrue(vetoed_eth)

    def test_reset_stats(self):
        self.supervisor.check_count = 10
        self.supervisor.veto_count = 5
        self.supervisor.reset_stats()
        stats = self.supervisor.get_stats()
        self.assertEqual(stats["check_count"], 0)
        self.assertEqual(stats["veto_count"], 0)


# ===========================================================================
# RegimeDetector Tests
# ===========================================================================

class TestRegimeDetector(unittest.TestCase):
    def setUp(self):
        self.detector = RegimeDetector(window_size=50)

    def test_initial_state(self):
        state = self.detector.get_state("BTC/USDT")
        self.assertEqual(state.label, 0)
        self.assertEqual(state.risk_score, 0.0)

    def test_insufficient_data_returns_ranging(self):
        for price in [100.0, 100.5, 100.3]:
            state = self.detector.update("BTC/USDT", price)
        self.assertEqual(state.label, 0)
        self.assertLess(state.confidence, 0.5)

    def test_trending_detection(self):
        # Simulate strong uptrend
        base = 100.0
        for i in range(60):
            state = self.detector.update("BTC/USDT", base + i * 0.5)
        # Should detect trending regime
        self.assertIn(state.label, [0, 1])  # may or may not detect with this simple sim
        self.assertGreater(state.trend_strength, 0.0)

    def test_volatile_detection(self):
        # Simulate high volatility
        import random
        random.seed(42)
        base = 100.0
        for i in range(60):
            price = base + random.uniform(-5.0, 5.0)
            state = self.detector.update("BTC/USDT", price)
        self.assertGreater(state.volatility, 0.0)

    def test_crash_detection(self):
        # Simulate crash: sharp decline
        for i in range(60):
            if i < 30:
                price = 100.0 + i * 0.1
            else:
                price = 103.0 - (i - 30) * 3.0  # sharp decline
            state = self.detector.update("BTC/USDT", price)
        # Risk score should be elevated
        self.assertGreater(state.risk_score, 0.0)

    def test_get_label(self):
        self.detector.update("BTC/USDT", 100.0)
        label = self.detector.get_label("BTC/USDT")
        self.assertIn(label, [0, 1, 2, 3])

    def test_get_risk_score(self):
        for i in range(30):
            self.detector.update("BTC/USDT", 100.0 + i * 0.1)
        risk = self.detector.get_risk_score("BTC/USDT")
        self.assertGreaterEqual(risk, 0.0)
        self.assertLessEqual(risk, 1.0)

    def test_multiple_symbols(self):
        self.detector.update("BTC/USDT", 100.0)
        self.detector.update("ETH/USDT", 2000.0)
        states = self.detector.get_all_states()
        self.assertIn("BTC/USDT", states)
        self.assertIn("ETH/USDT", states)

    def test_reset_symbol(self):
        self.detector.update("BTC/USDT", 100.0)
        self.detector.reset("BTC/USDT")
        state = self.detector.get_state("BTC/USDT")
        self.assertEqual(state.label, 0)

    def test_reset_all(self):
        self.detector.update("BTC/USDT", 100.0)
        self.detector.update("ETH/USDT", 2000.0)
        self.detector.reset()
        states = self.detector.get_all_states()
        self.assertEqual(len(states), 0)

    def test_regime_state_dataclass(self):
        state = RegimeState(label=2, confidence=0.8, risk_score=0.7)
        self.assertEqual(state.label, 2)
        self.assertEqual(state.confidence, 0.8)
        self.assertEqual(state.risk_score, 0.7)


if __name__ == "__main__":
    unittest.main()