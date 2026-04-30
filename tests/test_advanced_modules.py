"""Tests for Advanced Architecture Deep-Dive modules.

Covers:
- Prioritized Experience Replay Buffer (Phase D)
- Concept Drift Detector (Phase D)
- XAI Explainability Service (Phase F)
- Autonomy Slider Service (Phase G)
"""

from __future__ import annotations

import os
import sys
import tempfile
import time
import unittest

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ── Helper ────────────────────────────────────────────────────────────

def _make_experience(td_error=1.0, regime="unknown"):
    from src.rl.experience_replay import Experience
    return Experience(
        state=np.random.randn(10),
        action=np.random.randn(2),
        reward=float(np.random.randn()),
        next_state=np.random.randn(10),
        done=False,
        regime=regime,
        td_error=td_error,
    )


# ── Phase D: SumTree ─────────────────────────────────────────────────

class TestSumTree(unittest.TestCase):

    def _make_tree(self, capacity=8):
        from src.rl.experience_replay import SumTree
        return SumTree(capacity)

    def test_add_and_total(self):
        tree = self._make_tree(8)
        tree.add(1.0)
        tree.add(2.0)
        tree.add(3.0)
        self.assertAlmostEqual(tree.total, 6.0, places=5)

    def test_update_priority(self):
        tree = self._make_tree(8)
        tree.add(1.0)
        tree.add(2.0)
        tree.update(7, 5.0)
        self.assertAlmostEqual(tree.total, 7.0, places=5)

    def test_get_returns_valid_index(self):
        tree = self._make_tree(4)
        for v in [1.0, 2.0, 3.0, 4.0]:
            tree.add(v)
        tree_idx, priority, data_idx = tree.get(5.0)
        self.assertIsInstance(data_idx, int)
        self.assertGreaterEqual(data_idx, 0)
        self.assertLess(data_idx, 4)

    def test_min_priority(self):
        tree = self._make_tree(4)
        for v in [0.5, 2.0, 3.0, 4.0]:
            tree.add(v)
        self.assertAlmostEqual(tree.min(), 0.5, places=5)


# ── Phase D: PrioritizedReplayBuffer ─────────────────────────────────

class TestPrioritizedReplayBuffer(unittest.TestCase):

    def _make_buffer(self, capacity=100):
        from src.rl.experience_replay import PrioritizedReplayBuffer
        return PrioritizedReplayBuffer(capacity=capacity)

    def test_add_increases_size(self):
        buf = self._make_buffer(50)
        buf.add(_make_experience(td_error=1.0))
        buf.add(_make_experience(td_error=2.0))
        self.assertEqual(buf.size, 2)

    def test_sample_returns_correct_batch_size(self):
        buf = self._make_buffer(100)
        for _ in range(20):
            buf.add(_make_experience())
        exps, indices, weights = buf.sample(10)
        self.assertEqual(len(exps), 10)
        self.assertEqual(len(indices), 10)
        self.assertEqual(len(weights), 10)

    def test_sample_raises_if_not_enough(self):
        buf = self._make_buffer(100)
        buf.add(_make_experience())
        with self.assertRaises(ValueError):
            buf.sample(5)

    def test_is_weights_normalized(self):
        buf = self._make_buffer(100)
        for _ in range(50):
            buf.add(_make_experience(td_error=float(np.random.rand())))
        _, _, weights = buf.sample(16)
        self.assertAlmostEqual(float(weights.max()), 1.0, places=3)

    def test_update_priorities_changes_tree(self):
        buf = self._make_buffer(100)
        for _ in range(20):
            buf.add(_make_experience(td_error=1.0))
        _, indices, _ = buf.sample(5)
        new_tds = np.array([10.0, 20.0, 30.0, 40.0, 50.0])
        buf.update_priorities(indices, new_tds)
        self.assertGreater(buf._max_priority, 1.0)

    def test_regime_boost(self):
        buf = self._make_buffer(100)
        buf.add(_make_experience(td_error=1.0, regime="unknown"))
        buf.add(_make_experience(td_error=1.0, regime="trending"))
        self.assertEqual(buf.size, 2)

    def test_save_load(self):
        buf = self._make_buffer(50)
        for _ in range(10):
            buf.add(_make_experience(td_error=float(np.random.rand())))
        with tempfile.NamedTemporaryFile(suffix=".pkl", delete=False) as f:
            path = f.name
        try:
            buf.save(path)
            buf2 = self._make_buffer(50)
            buf2.load(path)
            self.assertEqual(buf2.size, 10)
        finally:
            os.unlink(path)

    def test_clear_resets_buffer(self):
        buf = self._make_buffer(50)
        for _ in range(10):
            buf.add(_make_experience())
        buf.clear()
        self.assertEqual(buf.size, 0)

    def test_stats(self):
        buf = self._make_buffer(100)
        for _ in range(5):
            buf.add(_make_experience())
        stats = buf.get_stats()
        self.assertEqual(stats["size"], 5)
        self.assertEqual(stats["capacity"], 100)

    def test_beta_annealing(self):
        from src.rl.experience_replay import PrioritizedReplayBuffer
        buf = PrioritizedReplayBuffer(capacity=100, beta_start=0.4, beta_frames=100)
        initial_beta = buf.beta
        buf._frame = 50
        mid_beta = buf.beta
        buf._frame = 100
        final_beta = buf.beta
        self.assertLessEqual(initial_beta, mid_beta)
        self.assertLessEqual(mid_beta, final_beta)
        self.assertAlmostEqual(final_beta, 1.0, places=2)

    def test_capacity_overflow(self):
        buf = self._make_buffer(5)
        for i in range(10):
            buf.add(_make_experience())
        self.assertEqual(buf.size, 5)


# ── Phase D: ConceptDriftDetector ────────────────────────────────────

class TestConceptDriftDetector(unittest.TestCase):

    def _make_detector(self, **kwargs):
        from src.rl.experience_replay import ConceptDriftDetector
        return ConceptDriftDetector(**kwargs)

    def test_no_drift_on_stable_series(self):
        det = self._make_detector(threshold=10.0, min_samples=10)
        for _ in range(50):
            result = det.update(float(np.random.normal(0, 0.1)))
        self.assertFalse(result)

    def test_drift_detected_on_shift(self):
        det = self._make_detector(threshold=2.0, min_samples=10)
        for _ in range(50):
            det.update(1.0)
        drift = False
        for _ in range(50):
            if det.update(100.0):
                drift = True
                break
        self.assertTrue(drift or det._drift_count > 0)

    def test_stats(self):
        det = self._make_detector()
        for _ in range(10):
            det.update(0.5)
        stats = det.get_stats()
        self.assertIn("total_updates", stats)
        self.assertIn("drift_count", stats)


# ── Phase F: XAI Service ─────────────────────────────────────────────

class TestXAIService(unittest.TestCase):

    def _make_service(self):
        from src.api.services.xai_service import XAIService
        return XAIService(
            feature_names=["rsi", "macd", "bb_width", "sentiment_score", "volatility"],
            top_k_features=3,
        )

    def _dummy_predict(self, obs):
        action = np.array([float(np.sum(obs[:3])) / 10.0])
        return action, {}

    def test_compute_feature_importance(self):
        svc = self._make_service()
        obs = np.array([0.5, 0.3, 0.8, -0.2, 0.1])
        contributions = svc.compute_feature_importance(
            obs, self._dummy_predict, n_perturbations=20,
        )
        self.assertEqual(len(contributions), 5)
        self.assertTrue(all(c.weight >= 0 for c in contributions))

    def test_generate_explanation_buy(self):
        from src.api.services.xai_service import FeatureImportance
        svc = self._make_service()
        contributions = [
            FeatureImportance("rsi", "RSI", 0.7, 0.5, "bullish", 0.4),
            FeatureImportance("macd", "MACD", 0.3, 0.3, "bullish", 0.3),
            FeatureImportance("bb_width", "BB Width", 0.2, 0.1, "neutral", 0.1),
            FeatureImportance("sentiment_score", "Sentiment", 0.5, 0.2, "bullish", 0.2),
        ]
        obs = np.array([0.7, 0.3, 0.2, 0.5, 0.1])
        exp = svc.generate_explanation(
            symbol="BTC/USDT",
            action_value=0.8,
            target_fraction=0.5,
            observation=obs,
            feature_contributions=contributions,
            regime="trending",
        )
        self.assertEqual(exp.action, "BUY")
        self.assertIn("BTC/USDT", exp.narrative)
        self.assertIn("trending", exp.regime_context.lower())
        self.assertGreater(exp.confidence_score, 0)

    def test_generate_explanation_sell(self):
        from src.api.services.xai_service import FeatureImportance
        svc = self._make_service()
        contributions = [
            FeatureImportance("rsi", "RSI", 0.2, 0.5, "bearish", 0.5),
            FeatureImportance("macd", "MACD", -0.3, 0.3, "bearish", 0.3),
            FeatureImportance("volatility", "Volatility", 0.9, 0.2, "bearish", 0.2),
        ]
        obs = np.array([0.2, -0.3, 0.1, -0.5, 0.9])
        exp = svc.generate_explanation(
            symbol="ETH/USDT",
            action_value=-0.6,
            target_fraction=-0.3,
            observation=obs,
            feature_contributions=contributions,
            regime="volatile",
            supervisor_flags=["MiMo: geopolitical risk elevated"],
        )
        self.assertEqual(exp.action, "SELL")
        self.assertIn("volatile", exp.regime_context.lower())
        self.assertGreater(len(exp.supervisor_flags), 0)

    def test_generate_explanation_hold(self):
        from src.api.services.xai_service import FeatureImportance
        svc = self._make_service()
        contributions = [
            FeatureImportance("rsi", "RSI", 0.5, 0.1, "neutral", 0.5),
            FeatureImportance("macd", "MACD", 0.0, 0.05, "neutral", 0.5),
        ]
        obs = np.array([0.5, 0.0, 0.1, 0.0, 0.1])
        exp = svc.generate_explanation(
            symbol="EUR/USD",
            action_value=0.05,
            target_fraction=0.0,
            observation=obs,
            feature_contributions=contributions,
        )
        self.assertEqual(exp.action, "HOLD")

    def test_risk_assessment_extreme(self):
        from src.api.services.xai_service import FeatureImportance
        svc = self._make_service()
        contributions = [
            FeatureImportance("liq", "Liquidation", 0.05, 0.5, "bearish", 0.5),
            FeatureImportance("vol", "Volatility", 0.9, 0.3, "bearish", 0.3),
            FeatureImportance("rsi", "RSI", 0.2, 0.2, "bearish", 0.2),
        ]
        obs = np.array([0.05, 0.9, 0.2, -0.5, 0.8])
        exp = svc.generate_explanation(
            symbol="BTC/USDT",
            action_value=0.9,
            target_fraction=0.95,
            observation=obs,
            feature_contributions=contributions,
            regime="crash",
        )
        self.assertIn("EXTREME", exp.risk_assessment)

    def test_history_and_stats(self):
        from src.api.services.xai_service import FeatureImportance
        svc = self._make_service()
        contributions = [
            FeatureImportance("rsi", "RSI", 0.5, 0.1, "neutral", 1.0),
        ]
        for _ in range(5):
            svc.generate_explanation(
                "BTC/USDT", 0.5, 0.3, np.array([0.5]), contributions,
            )
        self.assertEqual(len(svc.get_history()), 5)
        stats = svc.get_stats()
        self.assertEqual(stats["total_explanations"], 5)


# ── Phase G: Autonomy Service ────────────────────────────────────────

class TestAutonomyService(unittest.TestCase):

    def _make_service(self, level=1):
        from src.api.services.autonomy_service import AutonomyService, AutonomyLevel
        return AutonomyService(
            initial_level=AutonomyLevel(level),
            order_expiry_seconds=60.0,
        )

    def test_initial_level(self):
        svc = self._make_service(1)
        self.assertEqual(svc.level.value, 1)

    def test_set_level(self):
        svc = self._make_service(1)
        result = svc.set_level(3)
        self.assertTrue(result["success"])
        self.assertEqual(svc.level.value, 3)

    def test_set_invalid_level(self):
        svc = self._make_service(1)
        result = svc.set_level(5)
        self.assertFalse(result["success"])

    def test_kill_switch(self):
        svc = self._make_service(1)
        self.assertFalse(svc.kill_switch_active)
        svc.activate_kill_switch("test")
        self.assertTrue(svc.kill_switch_active)
        svc.deactivate_kill_switch()
        self.assertFalse(svc.kill_switch_active)

    def test_signal_only_mode(self):
        svc = self._make_service(1)
        result = svc.process_trade_signal(
            symbol="BTC/USDT", side="BUY", quantity=0.01,
            target_fraction=0.3, reason="test",
        )
        self.assertEqual(result["action"], "signal_only")

    def test_human_confirm_mode(self):
        svc = self._make_service(2)
        result = svc.process_trade_signal(
            symbol="BTC/USDT", side="BUY", quantity=0.01,
            target_fraction=0.3, reason="RSI oversold",
        )
        self.assertEqual(result["action"], "order_drafted")
        self.assertEqual(result["order"]["status"], "pending")

    def test_full_auto_mode(self):
        svc = self._make_service(3)
        result = svc.process_trade_signal(
            symbol="BTC/USDT", side="BUY", quantity=0.01,
            target_fraction=0.3, reason="momentum",
        )
        self.assertEqual(result["action"], "auto_execute")

    def test_approve_order(self):
        svc = self._make_service(2)
        result = svc.process_trade_signal(
            symbol="BTC/USDT", side="BUY", quantity=0.01,
            target_fraction=0.3, reason="test",
        )
        order_id = result["order"]["order_id"]
        approve_result = svc.approve_order(order_id)
        self.assertTrue(approve_result["success"])

    def test_reject_order(self):
        svc = self._make_service(2)
        result = svc.process_trade_signal(
            symbol="BTC/USDT", side="BUY", quantity=0.01,
            target_fraction=0.3, reason="test",
        )
        order_id = result["order"]["order_id"]
        reject_result = svc.reject_order(order_id, "too risky")
        self.assertTrue(reject_result["success"])
        self.assertEqual(reject_result["reason"], "too risky")

    def test_kill_switch_blocks_signals(self):
        svc = self._make_service(3)
        svc.activate_kill_switch("emergency")
        result = svc.process_trade_signal(
            symbol="BTC/USDT", side="BUY", quantity=0.01,
            target_fraction=0.3, reason="test",
        )
        self.assertEqual(result["action"], "blocked")

    def test_kill_switch_expires_pending(self):
        svc = self._make_service(2)
        svc.process_trade_signal(
            symbol="BTC/USDT", side="BUY", quantity=0.01,
            target_fraction=0.3, reason="test",
        )
        self.assertEqual(len(svc.get_pending_orders()), 1)
        svc.activate_kill_switch("emergency")
        self.assertEqual(len(svc.get_pending_orders()), 0)

    def test_approve_nonexistent_order(self):
        svc = self._make_service(2)
        result = svc.approve_order("FAKE-ID")
        self.assertFalse(result["success"])

    def test_get_state(self):
        svc = self._make_service(2)
        state = svc.get_state()
        self.assertEqual(state.level.value, 2)
        self.assertFalse(state.kill_switch_active)

    def test_stats(self):
        svc = self._make_service(3)
        for _ in range(3):
            svc.process_trade_signal(
                "BTC/USDT", "BUY", 0.01, 0.3, "test",
            )
        stats = svc.get_stats()
        self.assertEqual(stats["total_auto_executed"], 3)

    def test_pending_order_limit(self):
        svc = self._make_service(2)
        svc._max_pending = 3
        for i in range(5):
            svc.process_trade_signal(
                "BTC/USDT", "BUY", 0.01, 0.3, f"test {i}",
            )
        self.assertLessEqual(len(svc.get_pending_orders()), 3)


if __name__ == "__main__":
    unittest.main()