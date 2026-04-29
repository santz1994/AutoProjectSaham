"""Tests for MIMO LLM Connector (Phase 5 — Sentiment Integration).

Validates:
- SentimentResult data structure and vector output
- JSON parsing from LLM responses (including markdown fences)
- Connector configuration (env vars, defaults)
- SentimentScheduler lifecycle and thread safety
- RL agent sentiment vector augmentation in predict()
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import threading
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

# Ensure project root is on sys.path
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_THIS_DIR)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

import gymnasium
import numpy as np

from src.pipeline.data_connectors.mimo_llm_connector import (
    SentimentResult,
    MimoLLMConnector,
    analyze_sentiment_sync,
)


class TestSentimentResult(unittest.TestCase):
    """Tests for SentimentResult data class."""

    def test_default_values(self):
        r = SentimentResult()
        self.assertEqual(r.sentiment_score, 0.0)
        self.assertEqual(r.confidence, 0.0)
        self.assertEqual(r.key_factors, [])
        self.assertEqual(r.risk_level, "medium")
        self.assertEqual(r.market_regime_hint, "ranging")
        self.assertIsNone(r.error)

    def test_to_dict(self):
        r = SentimentResult(
            sentiment_score=0.75,
            confidence=0.9,
            key_factors=["BTC rally"],
            risk_level="low",
            market_regime_hint="trending_up",
        )
        d = r.to_dict()
        self.assertAlmostEqual(d["sentiment_score"], 0.75)
        self.assertAlmostEqual(d["confidence"], 0.9)
        self.assertEqual(d["key_factors"], ["BTC rally"])
        self.assertEqual(d["risk_level"], "low")
        self.assertEqual(d["market_regime_hint"], "trending_up")

    def test_to_vector_dimensions(self):
        r = SentimentResult(
            sentiment_score=0.5,
            confidence=0.8,
            risk_level="high",
            market_regime_hint="trending_down",
        )
        vec = r.to_vector()
        self.assertEqual(len(vec), 7)
        self.assertAlmostEqual(vec[0], 0.5)   # sentiment_score
        self.assertAlmostEqual(vec[1], 0.8)   # confidence
        self.assertAlmostEqual(vec[2], 0.75)  # risk_level "high" -> 0.75
        self.assertAlmostEqual(vec[3], 0.0)   # regime_up = False
        self.assertAlmostEqual(vec[4], 1.0)   # regime_down = True
        self.assertAlmostEqual(vec[5], 0.0)   # regime_ranging = False
        self.assertAlmostEqual(vec[6], 0.0)   # regime_volatile = False

    def test_to_vector_bullish(self):
        r = SentimentResult(
            sentiment_score=1.0,
            confidence=1.0,
            risk_level="low",
            market_regime_hint="trending_up",
        )
        vec = r.to_vector()
        self.assertAlmostEqual(vec[0], 1.0)
        self.assertAlmostEqual(vec[1], 1.0)
        self.assertAlmostEqual(vec[2], 0.15)
        self.assertAlmostEqual(vec[3], 1.0)
        self.assertAlmostEqual(vec[4], 0.0)

    def test_to_vector_neutral_default(self):
        r = SentimentResult()
        vec = r.to_vector()
        # default: score=0, conf=0, risk=medium(0.5), ranging=[0,0,1,0]
        self.assertAlmostEqual(vec[0], 0.0)
        self.assertAlmostEqual(vec[1], 0.0)
        self.assertAlmostEqual(vec[2], 0.45)
        self.assertAlmostEqual(vec[3], 0.0)
        self.assertAlmostEqual(vec[4], 0.0)
        self.assertAlmostEqual(vec[5], 1.0)
        self.assertAlmostEqual(vec[6], 0.0)

    def test_to_vector_extreme_risk_volatile(self):
        r = SentimentResult(
            sentiment_score=-0.8,
            confidence=0.95,
            risk_level="extreme",
            market_regime_hint="volatile",
        )
        vec = r.to_vector()
        self.assertAlmostEqual(vec[0], -0.8)
        self.assertAlmostEqual(vec[2], 1.0)  # extreme -> 1.0
        self.assertAlmostEqual(vec[3], 0.0)
        self.assertAlmostEqual(vec[4], 0.0)
        self.assertAlmostEqual(vec[5], 0.0)
        self.assertAlmostEqual(vec[6], 1.0)  # volatile


class TestMimoLLMConnectorParsing(unittest.TestCase):
    """Tests for JSON parsing logic."""

    def test_parse_clean_json(self):
        raw = json.dumps({
            "sentiment_score": 0.6,
            "confidence": 0.85,
            "key_factors": ["ETF approval"],
            "risk_level": "medium",
            "market_regime_hint": "trending_up",
        })
        parsed = MimoLLMConnector._parse_sentiment_json(raw)
        self.assertAlmostEqual(parsed["sentiment_score"], 0.6)
        self.assertEqual(len(parsed["key_factors"]), 1)

    def test_parse_markdown_fenced_json(self):
        raw = '```json\n{"sentiment_score": -0.3, "confidence": 0.7, "key_factors": [], "risk_level": "high", "market_regime_hint": "volatile"}\n```'
        parsed = MimoLLMConnector._parse_sentiment_json(raw)
        self.assertAlmostEqual(parsed["sentiment_score"], -0.3)
        self.assertEqual(parsed["risk_level"], "high")

    def test_parse_json_with_extra_text(self):
        raw = 'Here is the analysis:\n{"sentiment_score": 0.1, "confidence": 0.5, "key_factors": ["neutral"], "risk_level": "low", "market_regime_hint": "ranging"}\nEnd of analysis.'
        parsed = MimoLLMConnector._parse_sentiment_json(raw)
        self.assertAlmostEqual(parsed["sentiment_score"], 0.1)

    def test_parse_invalid_json_returns_empty(self):
        parsed = MimoLLMConnector._parse_sentiment_json("not json at all")
        self.assertEqual(parsed, {})


class TestMimoLLMConnectorConfig(unittest.TestCase):
    """Tests for connector configuration from env vars."""

    def test_default_model_id(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("MIMO_MODEL_ID", None)
            c = MimoLLMConnector(api_key="test-key")
            self.assertEqual(c.model_id, "mimoai/mimo-v2.5-pro")

    def test_custom_model_id(self):
        with patch.dict(os.environ, {"MIMO_MODEL_ID": "custom/model"}):
            c = MimoLLMConnector(api_key="test-key")
            self.assertEqual(c.model_id, "custom/model")

    def test_api_key_from_mimo_env(self):
        with patch.dict(os.environ, {"MIMO_API_KEY": "mimo-key-123"}):
            os.environ.pop("OPENROUTER_API_KEY", None)
            c = MimoLLMConnector()
            self.assertEqual(c.api_key, "mimo-key-123")

    def test_api_key_fallback_openrouter(self):
        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "or-key-456"}):
            os.environ.pop("MIMO_API_KEY", None)
            c = MimoLLMConnector()
            self.assertEqual(c.api_key, "or-key-456")

    def test_api_key_explicit_override(self):
        c = MimoLLMConnector(api_key="explicit-key")
        self.assertEqual(c.api_key, "explicit-key")

    def test_no_api_key_returns_error_result(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("MIMO_API_KEY", None)
            os.environ.pop("OPENROUTER_API_KEY", None)
            c = MimoLLMConnector()
            # Run async analyze_sentiment
            loop = asyncio.new_event_loop()
            result = loop.run_until_complete(c.analyze_sentiment("test"))
            loop.close()
            self.assertIsNotNone(result.error)
            self.assertIn("No API key", result.error)

    def test_stats(self):
        c = MimoLLMConnector(api_key="test-key")
        stats = c.get_stats()
        self.assertTrue(stats["has_api_key"])
        self.assertEqual(stats["request_count"], 0)
        self.assertEqual(stats["error_count"], 0)


class TestMimoLLMConnectorAsync(unittest.TestCase):
    """Tests for async API call behavior (mocked httpx)."""

    def test_successful_call(self):
        """Test that a successful API call produces a valid SentimentResult."""

        async def _run():
            mock_response_data = {
                "choices": [{
                    "message": {
                        "content": json.dumps({
                            "sentiment_score": 0.65,
                            "confidence": 0.88,
                            "key_factors": ["ETF approval", "institutional buying"],
                            "risk_level": "low",
                            "market_regime_hint": "trending_up",
                        })
                    }
                }]
            }

            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = mock_response_data
            mock_resp.raise_for_status = MagicMock()

            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_resp)
            mock_client.aclose = AsyncMock()

            connector = MimoLLMConnector(api_key="test-key")

            with patch.object(connector, "_get_client", return_value=mock_client):
                result = await connector.analyze_sentiment("Bitcoin ETF approved!")

            self.assertAlmostEqual(result.sentiment_score, 0.65)
            self.assertAlmostEqual(result.confidence, 0.88)
            self.assertEqual(result.risk_level, "low")
            self.assertEqual(result.market_regime_hint, "trending_up")
            self.assertEqual(len(result.key_factors), 2)
            self.assertIsNone(result.error)

        asyncio.run(_run())

    def test_batch_analysis(self):
        """Test batch analysis combines news items."""

        async def _run():
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = {
                "choices": [{"message": {"content": json.dumps({
                    "sentiment_score": 0.3,
                    "confidence": 0.7,
                    "key_factors": ["mixed signals"],
                    "risk_level": "medium",
                    "market_regime_hint": "ranging",
                })}}]
            }
            mock_resp.raise_for_status = MagicMock()

            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_resp)
            mock_client.aclose = AsyncMock()

            connector = MimoLLMConnector(api_key="test-key")

            with patch.object(connector, "_get_client", return_value=mock_client):
                result = await connector.analyze_batch([
                    "BTC surges 5%",
                    "Fed holds rates",
                    "ETH merge success",
                ])

            self.assertAlmostEqual(result.sentiment_score, 0.3)
            # Verify the prompt contained all 3 items
            call_args = mock_client.post.call_args
            payload = call_args[1]["json"] if "json" in call_args[1] else call_args[0][1]
            user_msg = payload["messages"][1]["content"]
            self.assertIn("[1]", user_msg)
            self.assertIn("[2]", user_msg)
            self.assertIn("[3]", user_msg)

        asyncio.run(_run())


class TestSentimentScheduler(unittest.TestCase):
    """Tests for SentimentScheduler."""

    def test_get_latest_vector_no_data(self):
        """Before any fetch cycle, vectors should return neutral defaults."""
        from src.pipeline.scheduler import SentimentScheduler

        sched = SentimentScheduler(symbols=["BTC/USDT"], interval_seconds=9999)
        vec = sched.get_latest_vector("BTC/USDT")
        self.assertEqual(len(vec), 7)
        self.assertAlmostEqual(vec[0], 0.0)
        self.assertAlmostEqual(vec[5], 1.0)  # ranging

    def test_get_latest_vector_unknown_symbol(self):
        from src.pipeline.scheduler import SentimentScheduler

        sched = SentimentScheduler(symbols=["BTC/USDT"], interval_seconds=9999)
        vec = sched.get_latest_vector("UNKNOWN/PAIR")
        self.assertEqual(len(vec), 7)
        self.assertAlmostEqual(vec[0], 0.0)

    def test_get_all_vectors_empty(self):
        from src.pipeline.scheduler import SentimentScheduler

        sched = SentimentScheduler(symbols=["BTC/USDT", "ETH/USDT"], interval_seconds=9999)
        all_vecs = sched.get_all_vectors()
        self.assertEqual(len(all_vecs), 0)

    def test_get_stats(self):
        from src.pipeline.scheduler import SentimentScheduler

        sched = SentimentScheduler(symbols=["BTC/USDT"], interval_seconds=3600)
        stats = sched.get_stats()
        self.assertEqual(stats["symbols"], ["BTC/USDT"])
        self.assertEqual(stats["interval_seconds"], 3600)
        self.assertEqual(stats["cycle_count"], 0)
        self.assertFalse(stats["is_running"])

    def test_manual_vector_injection(self):
        """Simulate manual vector injection as SentimentScheduler would do internally."""
        from src.pipeline.scheduler import SentimentScheduler
        from src.pipeline.data_connectors.mimo_llm_connector import SentimentResult

        sched = SentimentScheduler(symbols=["BTC/USDT"], interval_seconds=9999)

        # Simulate what _fetch_sentiment_cycle does
        result = SentimentResult(
            sentiment_score=0.8,
            confidence=0.95,
            risk_level="low",
            market_regime_hint="trending_up",
        )
        with sched._lock:
            sched.latest_sentiment["BTC/USDT"] = result
            sched.latest_vectors["BTC/USDT"] = result.to_vector()

        vec = sched.get_latest_vector("BTC/USDT")
        self.assertAlmostEqual(vec[0], 0.8)
        self.assertAlmostEqual(vec[1], 0.95)
        self.assertAlmostEqual(vec[2], 0.15)
        self.assertAlmostEqual(vec[3], 1.0)

        all_vecs = sched.get_all_vectors()
        self.assertIn("BTC/USDT", all_vecs)
        self.assertEqual(len(all_vecs["BTC/USDT"]), 7)


class TestRLAgentSentimentIntegration(unittest.TestCase):
    """Test that RLTradingAgent.predict() correctly augments features with sentiment."""

    def test_predict_without_sentiment(self):
        """predict() without sentiment_vector should work normally."""
        try:
            from stable_baselines3 import PPO
        except ImportError:
            self.skipTest("stable-baselines3 not installed")

        from src.rl.agent_integration import RLTradingAgent
        import tempfile, os

        # Create a minimal PPO model
        from gymnasium import spaces
        obs_space = spaces.Box(low=-1, high=1, shape=(10,), dtype=np.float32)
        act_space = spaces.Box(low=0, high=1, shape=(2,), dtype=np.float32)

        with tempfile.TemporaryDirectory() as td:
            model_path = os.path.join(td, "test_model")
            model = PPO("MlpPolicy", DummyGymEnv(obs_space, act_space), verbose=0)
            model.save(model_path)

            agent = RLTradingAgent(
                model_path=model_path,
                symbols=["BTC/USDT", "ETH/USDT"],
                model_type="ppo",
            )

            features = np.random.randn(10).astype(np.float32)
            action, state = agent.predict(features, deterministic=True)
            self.assertEqual(action.shape[0], 2)

    def test_predict_with_sentiment(self):
        """predict() with sentiment_vector should concatenate and still work."""
        try:
            from stable_baselines3 import PPO
        except ImportError:
            self.skipTest("stable-baselines3 not installed")

        from src.rl.agent_integration import RLTradingAgent
        import tempfile, os

        from gymnasium import spaces
        # 10 features + 7 sentiment = 17 total
        obs_space = spaces.Box(low=-1, high=1, shape=(17,), dtype=np.float32)
        act_space = spaces.Box(low=0, high=1, shape=(2,), dtype=np.float32)

        with tempfile.TemporaryDirectory() as td:
            model_path = os.path.join(td, "test_model")
            model = PPO("MlpPolicy", DummyGymEnv(obs_space, act_space), verbose=0)
            model.save(model_path)

            agent = RLTradingAgent(
                model_path=model_path,
                symbols=["BTC/USDT", "ETH/USDT"],
                model_type="ppo",
            )

            features = np.random.randn(10).astype(np.float32)
            sentiment = np.array([0.5, 0.8, 0.45, 1.0, 0.0, 0.0, 0.0], dtype=np.float32)
            action, state = agent.predict(features, deterministic=True, sentiment_vector=sentiment)
            self.assertEqual(action.shape[0], 2)
            # Verify the last_observation includes sentiment
            self.assertEqual(len(agent.last_observation), 17)


class DummyGymEnv(gymnasium.Env):
    """Minimal gymnasium-compatible env for model creation in tests."""

    metadata = {"render_modes": []}

    def __init__(self, obs_space, act_space):
        super().__init__()
        self.observation_space = obs_space
        self.action_space = act_space

    def reset(self, *, seed=None, options=None):
        super().reset(seed=seed)
        return self.observation_space.sample(), {}

    def step(self, action):
        obs = self.observation_space.sample()
        return obs, 0.0, False, False, {}


if __name__ == "__main__":
    unittest.main()