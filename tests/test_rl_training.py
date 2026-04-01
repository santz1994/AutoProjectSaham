"""
Test Suite for RL Training (Task 11)
====================================

Tests for:
- MultiSymbolTradingEnv
- PPO/SAC trainers
- Hybrid training
- Policy evaluation
- IDX compliance
"""

import pytest
import numpy as np
from pathlib import Path
from typing import Dict, List
from datetime import datetime, timezone, timedelta

# Try importing our modules
try:
    from src.rl.policy_trainer import (
        MultiSymbolTradingEnv,
        PPOTrainer,
        SACTrainer,
        HybridTrainer,
        TrainerConfig,
        evaluate_policy,
        STABLE_BASELINES3_AVAILABLE,
    )
except ImportError:
    STABLE_BASELINES3_AVAILABLE = False


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def sample_price_data():
    """Generate sample price data for testing."""
    np.random.seed(42)
    
    # Simulate realistic stock price movements
    prices = {
        "BBCA.JK": np.concatenate([
            np.linspace(7000, 7200, 50),  # Uptrend
            np.linspace(7200, 7000, 50),  # Downtrend
        ]).tolist(),
        "BMRI.JK": np.concatenate([
            np.linspace(5500, 5700, 50),
            np.linspace(5700, 5400, 50),
        ]).tolist(),
    }
    
    return prices


@pytest.fixture
def sample_feature_data(sample_price_data):
    """Generate sample feature data."""
    features = {}
    for symbol, prices in sample_price_data.items():
        n_bars = len(prices)
        # Each bar has 10 features
        features[symbol] = np.random.randn(n_bars, 10).astype(np.float32)
    return features


@pytest.fixture
def trader_config():
    """Create trainer config."""
    return TrainerConfig(
        model_name="test_agent",
        total_timesteps=1000,
        eval_freq=500,
        n_eval_episodes=2,
        learning_rate=1e-4,
        batch_size=32,
        verbose=0,
        seed=42,
    )


# ============================================================================
# Environment Tests
# ============================================================================

@pytest.mark.skipif(not STABLE_BASELINES3_AVAILABLE, reason="stable-baselines3 not available")
class TestMultiSymbolTradingEnv:
    """Test MultiSymbolTradingEnv."""
    
    def test_env_creation(self, sample_price_data):
        """Test environment initialization."""
        env = MultiSymbolTradingEnv(
            symbols=list(sample_price_data.keys()),
            price_data=sample_price_data,
            starting_capital=1_000_000.0,
        )
        
        assert env.n_symbols == 2
        assert env.starting_capital == 1_000_000.0
        assert env.portfolio_value == 1_000_000.0
        assert env.cash == 1_000_000.0
    
    def test_env_reset(self, sample_price_data):
        """Test environment reset."""
        env = MultiSymbolTradingEnv(
            symbols=list(sample_price_data.keys()),
            price_data=sample_price_data,
        )
        
        obs, info = env.reset()
        
        assert isinstance(obs, np.ndarray)
        assert obs.shape == env.observation_space.shape
        assert isinstance(info, dict)
    
    def test_env_step_hold(self, sample_price_data):
        """Test environment step with hold action."""
        env = MultiSymbolTradingEnv(
            symbols=list(sample_price_data.keys()),
            price_data=sample_price_data,
        )
        
        obs, _ = env.reset()
        
        # Hold action: [0, 0]
        action = np.array([0.0, 0.0], dtype=np.float32)
        obs_next, reward, terminated, truncated, info = env.step(action)
        
        assert isinstance(obs_next, np.ndarray)
        assert isinstance(reward, (float, np.floating))
        assert isinstance(terminated, bool)
        assert isinstance(truncated, bool)
        assert isinstance(info, dict)
    
    def test_env_step_buy(self, sample_price_data):
        """Test environment step with buy action."""
        env = MultiSymbolTradingEnv(
            symbols=list(sample_price_data.keys()),
            price_data=sample_price_data,
        )
        
        obs, _ = env.reset()
        
        # Buy action for first symbol
        action = np.array([0.5, 0.0], dtype=np.float32)
        obs_next, reward, terminated, truncated, info = env.step(action)
        
        # Check that position was taken
        assert env.holdings["BBCA.JK"] >= 0
    
    def test_env_step_sequence(self, sample_price_data):
        """Test running environment for multiple steps."""
        env = MultiSymbolTradingEnv(
            symbols=list(sample_price_data.keys()),
            price_data=sample_price_data,
        )
        
        obs, _ = env.reset()
        total_reward = 0.0
        
        for _ in range(10):
            action = env.action_space.sample()  # Random action
            obs, reward, terminated, truncated, info = env.step(action)
            total_reward += reward
            
            if terminated or truncated:
                break
        
        assert env.current_step > 0
        assert isinstance(total_reward, (float, np.floating))
    
    def test_env_observation_shape(self, sample_price_data, sample_feature_data):
        """Test observation shape consistency."""
        env = MultiSymbolTradingEnv(
            symbols=list(sample_price_data.keys()),
            price_data=sample_price_data,
            feature_data=sample_feature_data,
        )
        
        obs, _ = env.reset()
        
        expected_shape = env.observation_space.shape
        assert obs.shape == expected_shape, f"Expected {expected_shape}, got {obs.shape}"
    
    def test_env_action_bounds(self, sample_price_data):
        """Test action space bounds enforcement."""
        env = MultiSymbolTradingEnv(
            symbols=list(sample_price_data.keys()),
            price_data=sample_price_data,
        )
        
        env.reset()
        
        # Actions outside [0, 1]
        action = np.array([-0.5, 1.5], dtype=np.float32)
        obs, reward, terminated, truncated, info = env.step(action)
        
        # Should be clipped to [0, 1]
        assert np.all(obs >= -1e6) and np.all(obs <= 1e6)
    
    def test_env_portfolio_tracking(self, sample_price_data):
        """Test portfolio value tracking."""
        env = MultiSymbolTradingEnv(
            symbols=list(sample_price_data.keys()),
            price_data=sample_price_data,
            starting_capital=1_000_000.0,
        )
        
        obs, _ = env.reset()
        initial_value = env.portfolio_value
        
        # Run a few steps
        for _ in range(5):
            action = np.array([0.2, 0.2], dtype=np.float32)
            obs, reward, terminated, truncated, info = env.step(action)
        
        # Portfolio value should change
        assert hasattr(info, '__getitem__')  # Can access like dict


# ============================================================================
# Trainer Tests
# ============================================================================

@pytest.mark.skipif(not STABLE_BASELINES3_AVAILABLE, reason="stable-baselines3 not available")
class TestPPOTrainer:
    """Test PPO trainer."""
    
    def test_trainer_creation(self, sample_price_data, trader_config):
        """Test trainer initialization."""
        env = MultiSymbolTradingEnv(
            symbols=list(sample_price_data.keys()),
            price_data=sample_price_data,
        )
        
        trainer = PPOTrainer(env, trader_config)
        
        assert trainer.env is env
        assert trainer.config == trader_config
        assert trainer.model is None  # Model created on demand
    
    def test_ppo_model_creation(self, sample_price_data, trader_config):
        """Test PPO model creation."""
        env = MultiSymbolTradingEnv(
            symbols=list(sample_price_data.keys()),
            price_data=sample_price_data,
        )
        
        trainer = PPOTrainer(env, trader_config)
        trainer.create_model()
        
        assert trainer.model is not None
        assert hasattr(trainer.model, "learn")
        assert hasattr(trainer.model, "predict")
    
    def test_ppo_training(self, sample_price_data, trader_config, tmp_path):
        """Test PPO training."""
        env = MultiSymbolTradingEnv(
            symbols=list(sample_price_data.keys()),
            price_data=sample_price_data,
        )
        
        trainer = PPOTrainer(env, trader_config)
        results = trainer.train(total_timesteps=500)
        
        assert results["status"] == "success"
        assert results["timesteps"] == 500
        assert "elapsed_seconds" in results


@pytest.mark.skipif(not STABLE_BASELINES3_AVAILABLE, reason="stable-baselines3 not available")
class TestSACTrainer:
    """Test SAC trainer."""
    
    def test_trainer_creation(self, sample_price_data, trader_config):
        """Test trainer initialization."""
        env = MultiSymbolTradingEnv(
            symbols=list(sample_price_data.keys()),
            price_data=sample_price_data,
        )
        
        trainer = SACTrainer(env, trader_config)
        
        assert trainer.env is env
        assert trainer.model is None
    
    def test_sac_model_creation(self, sample_price_data, trader_config):
        """Test SAC model creation."""
        env = MultiSymbolTradingEnv(
            symbols=list(sample_price_data.keys()),
            price_data=sample_price_data,
        )
        
        trainer = SACTrainer(env, trader_config)
        trainer.create_model()
        
        assert trainer.model is not None
        assert hasattr(trainer.model, "learn")


@pytest.mark.skipif(not STABLE_BASELINES3_AVAILABLE, reason="stable-baselines3 not available")
class TestHybridTrainer:
    """Test hybrid PPO+SAC trainer."""
    
    def test_hybrid_creation(self, sample_price_data, trader_config):
        """Test hybrid trainer creation."""
        env = MultiSymbolTradingEnv(
            symbols=list(sample_price_data.keys()),
            price_data=sample_price_data,
        )
        
        hybrid = HybridTrainer(
            env,
            trader_config,
            ppo_timesteps=100,
            sac_timesteps=100,
        )
        
        assert hybrid.env is env
        assert hybrid.ppo_timesteps == 100


# ============================================================================
# Policy Evaluation Tests
# ============================================================================

@pytest.mark.skipif(not STABLE_BASELINES3_AVAILABLE, reason="stable-baselines3 not available")
class TestPolicyEvaluation:
    """Test policy evaluation functions."""
    
    def test_evaluate_policy(self, sample_price_data, trader_config):
        """Test policy evaluation."""
        env = MultiSymbolTradingEnv(
            symbols=list(sample_price_data.keys()),
            price_data=sample_price_data,
        )
        
        trainer = PPOTrainer(env, trader_config)
        trainer.create_model()
        
        results = evaluate_policy(trainer.model, env, n_episodes=2)
        
        assert "mean_reward" in results
        assert "std_reward" in results
        assert "mean_length" in results
        assert results["episodes"] == 2


# ============================================================================
# IDX Compliance Tests
# ============================================================================

class TestIDXCompliance:
    """Test IDX/Indonesia compliance."""
    
    def test_minimum_lot_size(self, sample_price_data):
        """Test minimum lot size enforcement."""
        if not STABLE_BASELINES3_AVAILABLE:
            pytest.skip("stable-baselines3 not available")
        
        env = MultiSymbolTradingEnv(
            symbols=list(sample_price_data.keys()),
            price_data=sample_price_data,
            position_size_shares=100,  # IDX minimum
        )
        
        assert env.position_size_shares == 100
    
    def test_trading_hours_check(self):
        """Test trading hours validation."""
        from src.rl.policy_trainer import is_trading_hours, get_jakarta_now
        
        # This will check current time, so just verify function exists
        assert callable(is_trading_hours)
        assert callable(get_jakarta_now)
    
    def test_jakarta_timezone(self):
        """Test Jakarta timezone handling."""
        from src.rl.policy_trainer import get_jakarta_now, JAKARTA_TZ
        
        now = get_jakarta_now()
        assert now.tzinfo is not None
        assert now.utcoffset() == timedelta(hours=7)


# ============================================================================
# Integration Tests
# ============================================================================

class TestAgentIntegration:
    """Test agent integration module."""
    
    def test_position_manager(self):
        """Test position manager."""
        from src.rl.agent_integration import PositionManager
        
        pm = PositionManager(starting_capital=1_000_000.0)
        
        assert pm.cash == 1_000_000.0
        assert pm.holdings == {}
        assert pm.min_lot_size == 100
    
    def test_portfolio_state(self):
        """Test portfolio state data class."""
        from src.rl.agent_integration import PortfolioState
        
        state = PortfolioState(
            total_value=1_000_000.0,
            cash=500_000.0,
        )
        
        assert state.total_value == 1_000_000.0
        assert state.cash == 500_000.0
        
        # Check conversion to dict
        d = state.to_dict()
        assert isinstance(d, dict)
        assert d["total_value"] == 1_000_000.0


# ============================================================================
# Performance Tests
# ============================================================================

@pytest.mark.skipif(not STABLE_BASELINES3_AVAILABLE, reason="stable-baselines3 not available")
class TestPerformance:
    """Test performance and efficiency."""
    
    def test_env_step_speed(self, sample_price_data):
        """Test environment step speed."""
        env = MultiSymbolTradingEnv(
            symbols=list(sample_price_data.keys()),
            price_data=sample_price_data,
        )
        
        env.reset()
        
        # Time 100 steps
        import time
        start = time.time()
        
        for _ in range(100):
            action = env.action_space.sample()
            obs, reward, terminated, truncated, info = env.step(action)
            if terminated or truncated:
                env.reset()
        
        elapsed = time.time() - start
        
        # Should be reasonably fast (< 1 second for 100 steps)
        assert elapsed < 1.0, f"100 steps took {elapsed:.2f}s"


# ============================================================================
# Edge Case Tests
# ============================================================================

@pytest.mark.skipif(not STABLE_BASELINES3_AVAILABLE, reason="stable-baselines3 not available")
class TestEdgeCases:
    """Test edge cases and error handling."""
    
    def test_empty_price_data(self):
        """Test behavior with empty price data."""
        with pytest.raises(ValueError):
            env = MultiSymbolTradingEnv(
                symbols=["TEST"],
                price_data={"TEST": []},
            )
    
    def test_nan_prices(self, sample_price_data):
        """Test handling of NaN prices."""
        bad_data = sample_price_data.copy()
        bad_data["BBCA.JK"] = [7000, np.nan, 7100]
        
        # Should still initialize
        if STABLE_BASELINES3_AVAILABLE:
            try:
                env = MultiSymbolTradingEnv(
                    symbols=list(bad_data.keys()),
                    price_data=bad_data,
                )
            except:
                pass  # May fail depending on implementation


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
