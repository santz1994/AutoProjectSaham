"""
Integration Tests for RL Agent (Task 11)
=========================================

Tests for:
- RLTradingAgent
- PositionManager
- Batch inference engine
- Integration with anomaly/regime detectors
"""

import pytest
import numpy as np
import tempfile
from pathlib import Path
from unittest.mock import Mock, MagicMock
from typing import Dict, List

try:
    from src.rl.agent_integration import (
        RLTradingAgent,
        PositionManager,
        PortfolioState,
        BatchInferenceEngine,
        STABLE_BASELINES3_AVAILABLE,
    )
    from src.rl.policy_trainer import MultiSymbolTradingEnv, PPOTrainer, TrainerConfig
except ImportError:
    STABLE_BASELINES3_AVAILABLE = False


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def sample_prices():
    """Sample price data."""
    return {
        "BTCUSDT": 7500.0,
        "ETHUSDT": 5600.0,
        "XRPUSDT": 3400.0,
    }


@pytest.fixture
def mock_anomaly_detector():
    """Mock anomaly detector."""
    detector = Mock()
    detector.is_anomaly = Mock(return_value=False)
    return detector


@pytest.fixture
def mock_regime_detector():
    """Mock regime detector."""
    detector = Mock()
    detector.get_regime = Mock(return_value="bull")
    detector.get_strategy_params = Mock(return_value={
        "risk_multiplier": 1.0,
        "position_size": 1.0,
    })
    return detector


# ============================================================================
# PositionManager Tests
# ============================================================================

class TestPositionManager:
    """Test position management."""
    
    def test_init(self):
        """Test initialization."""
        pm = PositionManager(
            starting_capital=1_000_000.0,
            min_lot_size=100,
            max_leverage=0.8,
        )
        
        assert pm.starting_capital == 1_000_000.0
        assert pm.cash == 1_000_000.0
        assert pm.min_lot_size == 100
        assert pm.max_leverage == 0.8
        assert pm.holdings == {}
    
    def test_get_state_empty(self, sample_prices):
        """Test portfolio state when no positions."""
        pm = PositionManager(starting_capital=1_000_000.0)
        state = pm.get_state(sample_prices)
        
        assert isinstance(state, PortfolioState)
        assert state.total_value == 1_000_000.0
        assert state.cash == 1_000_000.0
        assert state.daily_return == 0.0
    
    def test_get_state_with_positions(self, sample_prices):
        """Test portfolio state with positions."""
        pm = PositionManager(starting_capital=1_000_000.0)
        pm.holdings["BTCUSDT"] = 1000
        pm.entry_prices["BTCUSDT"] = 7000.0
        pm.cash = 900_000.0
        
        state = pm.get_state(sample_prices)
        
        assert state.holdings["BTCUSDT"] == 1000
        assert state.total_value > 1_000_000.0  # Prices went up
    
    def test_should_trade_valid_buy(self, sample_prices):
        """Test trade validation for valid buy."""
        pm = PositionManager(starting_capital=1_000_000.0)
        
        allowed, msg = pm.should_trade("BTCUSDT", 100, 7500.0)
        
        assert allowed
        assert msg == "OK"
    
    def test_should_trade_insufficient_cash(self, sample_prices):
        """Test trade validation when insufficient cash."""
        pm = PositionManager(starting_capital=100.0)  # Very small capital
        
        allowed, msg = pm.should_trade("BTCUSDT", 1000, 7500.0)
        
        assert not allowed
        assert "Insufficient cash" in msg
    
    def test_should_trade_not_multiple_of_lot(self, sample_prices):
        """Test trade validation for non-multiple lot size."""
        pm = PositionManager(starting_capital=1_000_000.0, min_lot_size=100)
        
        # 150 is not a multiple of 100
        allowed, msg = pm.should_trade("BTCUSDT", 150, 7500.0)
        
        assert not allowed
        assert "multiple" in msg
    
    def test_execute_buy_trade(self, sample_prices):
        """Test executing a buy trade."""
        pm = PositionManager(starting_capital=1_000_000.0)
        
        result = pm.execute_trade(
            symbol="BTCUSDT",
            action="buy",
            qty=1000,
            price=7500.0,
        )
        
        assert result["status"] == "executed"
        assert pm.holdings["BTCUSDT"] == 1000
        assert pm.cash < 1_000_000.0
    
    def test_execute_sell_trade(self, sample_prices):
        """Test executing a sell trade."""
        pm = PositionManager(starting_capital=1_000_000.0)
        
        # First buy
        pm.execute_trade("BTCUSDT", "buy", 1000, 7000.0)
        initial_cash = pm.cash
        
        # Then sell
        result = pm.execute_trade("BTCUSDT", "sell", 500, 7500.0)
        
        assert result["status"] == "executed"
        assert pm.holdings["BTCUSDT"] == 500
        assert pm.cash > initial_cash
    
    def test_trade_history_tracking(self, sample_prices):
        """Test trade history is tracked."""
        pm = PositionManager(starting_capital=1_000_000.0)
        
        pm.execute_trade("BTCUSDT", "buy", 100, 7500.0)
        pm.execute_trade("ETHUSDT", "buy", 200, 5600.0)
        
        assert len(pm.trade_history) == 2
        assert pm.trade_history[0]["symbol"] == "BTCUSDT"
        assert pm.trade_history[1]["symbol"] == "ETHUSDT"
    
    def test_pnl_tracking(self, sample_prices):
        """Test P&L tracking on sales."""
        pm = PositionManager(starting_capital=1_000_000.0)
        
        # Buy at 7000
        pm.execute_trade("BTCUSDT", "buy", 100, 7000.0)
        
        # Sell at 7500 (profit)
        pm.execute_trade("BTCUSDT", "sell", 100, 7500.0)
        
        assert pm.win_count == 1
        assert len(pm.pnl_history) == 1


# ============================================================================
# PortfolioState Tests
# ============================================================================

class TestPortfolioState:
    """Test portfolio state data class."""
    
    def test_creation(self):
        """Test creating portfolio state."""
        state = PortfolioState(
            total_value=1_000_000.0,
            cash=500_000.0,
            holdings={"BTCUSDT": 1000},
        )
        
        assert state.total_value == 1_000_000.0
        assert state.cash == 500_000.0
        assert state.holdings["BTCUSDT"] == 1000
    
    def test_to_dict(self):
        """Test conversion to dict."""
        state = PortfolioState(
            total_value=1_000_000.0,
            cash=500_000.0,
        )
        
        d = state.to_dict()
        
        assert isinstance(d, dict)
        assert d["total_value"] == 1_000_000.0
        assert d["cash"] == 500_000.0


# ============================================================================
# RLTradingAgent Tests
# ============================================================================

@pytest.mark.skipif(not STABLE_BASELINES3_AVAILABLE, reason="stable-baselines3 not available")
class TestRLTradingAgent:
    """Test RL trading agent."""
    
    def test_agent_creation(self, tmp_path, sample_prices):
        """Test agent creation with trained model."""
        # First create and train a simple model
        price_data = {
            "BTCUSDT": np.linspace(7000, 7200, 50).tolist(),
            "ETHUSDT": np.linspace(5500, 5700, 50).tolist(),
        }
        
        env = MultiSymbolTradingEnv(
            symbols=["BTCUSDT", "ETHUSDT"],
            price_data=price_data,
        )
        
        config = TrainerConfig(
            total_timesteps=500,
            verbose=0,
        )
        
        trainer = PPOTrainer(env, config)
        trainer.train(total_timesteps=500)
        
        # Save model
        model_path = str(tmp_path / "test_model.zip")
        trainer.save(model_path)
        
        # Create agent
        agent = RLTradingAgent(
            model_path=model_path,
            symbols=["BTCUSDT", "ETHUSDT"],
        )
        
        assert agent.model is not None
        assert agent.symbols == ["BTCUSDT", "ETHUSDT"]
    
    def test_predict(self, tmp_path, sample_prices):
        """Test agent prediction."""
        # Create and train a model
        price_data = {
            "BTCUSDT": np.linspace(7000, 7200, 50).tolist(),
            "ETHUSDT": np.linspace(5500, 5700, 50).tolist(),
        }
        
        env = MultiSymbolTradingEnv(
            symbols=["BTCUSDT", "ETHUSDT"],
            price_data=price_data,
        )
        
        config = TrainerConfig(total_timesteps=500, verbose=0)
        trainer = PPOTrainer(env, config)
        trainer.train(total_timesteps=500)
        
        model_path = str(tmp_path / "test_model.zip")
        trainer.save(model_path)
        
        agent = RLTradingAgent(model_path=model_path, symbols=["BTCUSDT", "ETHUSDT"])
        
        # Create observation
        obs = np.zeros(env.observation_space.shape, dtype=np.float32)
        
        action, state = agent.predict(obs, deterministic=True)
        
        assert isinstance(action, (np.ndarray, float))
    
    def test_process_action(self, tmp_path, sample_prices):
        """Test processing RL action into trades."""
        # Create a trained model
        price_data = {
            "BTCUSDT": np.linspace(7000, 7200, 50).tolist(),
            "ETHUSDT": np.linspace(5500, 5700, 50).tolist(),
        }
        
        env = MultiSymbolTradingEnv(
            symbols=["BTCUSDT", "ETHUSDT"],
            price_data=price_data,
        )
        
        config = TrainerConfig(total_timesteps=500, verbose=0)
        trainer = PPOTrainer(env, config)
        trainer.train(total_timesteps=500)
        
        model_path = str(tmp_path / "test_model.zip")
        trainer.save(model_path)
        
        agent = RLTradingAgent(model_path=model_path, symbols=["BTCUSDT", "ETHUSDT"])
        
        action = np.array([0.5, 0.3], dtype=np.float32)
        
        result = agent.process_action(
            action=action,
            current_prices=sample_prices,
        )
        
        assert "trades" in result
        assert "portfolio_state" in result
        assert "timestamp" in result
    
    def test_get_portfolio_state(self, tmp_path, sample_prices):
        """Test getting portfolio state."""
        price_data = {s: [p] * 10 for s, p in sample_prices.items()}
        
        env = MultiSymbolTradingEnv(
            symbols=list(sample_prices.keys()),
            price_data=price_data,
        )
        
        config = TrainerConfig(total_timesteps=100, verbose=0)
        trainer = PPOTrainer(env, config)
        trainer.train(total_timesteps=100)
        
        model_path = str(tmp_path / "test_model.zip")
        trainer.save(model_path)
        
        agent = RLTradingAgent(
            model_path=model_path,
            symbols=list(sample_prices.keys()),
        )
        
        state = agent.get_portfolio_state(sample_prices)
        
        assert isinstance(state, PortfolioState)
        assert state.total_value > 0
        assert state.cash > 0
    
    def test_checkpoint_saving(self, tmp_path, sample_prices):
        """Test saving agent checkpoint."""
        price_data = {s: [p] * 10 for s, p in sample_prices.items()}
        
        env = MultiSymbolTradingEnv(
            symbols=list(sample_prices.keys()),
            price_data=price_data,
        )
        
        config = TrainerConfig(total_timesteps=100, verbose=0)
        trainer = PPOTrainer(env, config)
        trainer.train(total_timesteps=100)
        
        model_path = str(tmp_path / "test_model.zip")
        trainer.save(model_path)
        
        agent = RLTradingAgent(
            model_path=model_path,
            symbols=list(sample_prices.keys()),
        )
        
        checkpoint_path = str(tmp_path / "checkpoint.json")
        success = agent.save_checkpoint(checkpoint_path)
        
        assert success
        assert Path(checkpoint_path).exists()
    
    def test_get_stats(self, tmp_path, sample_prices):
        """Test getting agent statistics."""
        price_data = {s: [p] * 10 for s, p in sample_prices.items()}
        
        env = MultiSymbolTradingEnv(
            symbols=list(sample_prices.keys()),
            price_data=price_data,
        )
        
        config = TrainerConfig(total_timesteps=100, verbose=0)
        trainer = PPOTrainer(env, config)
        trainer.train(total_timesteps=100)
        
        model_path = str(tmp_path / "test_model.zip")
        trainer.save(model_path)
        
        agent = RLTradingAgent(
            model_path=model_path,
            symbols=list(sample_prices.keys()),
        )
        
        stats = agent.get_stats()
        
        assert "model_path" in stats
        assert "symbols" in stats
        assert "inference_count" in stats
        assert "position_manager" in stats


# ============================================================================
# Batch Inference Tests
# ============================================================================

@pytest.mark.skipif(not STABLE_BASELINES3_AVAILABLE, reason="stable-baselines3 not available")
class TestBatchInferenceEngine:
    """Test batch inference engine."""
    
    def test_batch_engine_creation(self, tmp_path, sample_prices):
        """Test creating batch inference engine."""
        price_data = {s: [p] * 10 for s, p in sample_prices.items()}
        
        env = MultiSymbolTradingEnv(
            symbols=list(sample_prices.keys()),
            price_data=price_data,
        )
        
        config = TrainerConfig(total_timesteps=100, verbose=0)
        trainer = PPOTrainer(env, config)
        trainer.train(total_timesteps=100)
        
        model_path = str(tmp_path / "test_model.zip")
        trainer.save(model_path)
        
        agent = RLTradingAgent(
            model_path=model_path,
            symbols=list(sample_prices.keys()),
        )
        
        batch_engine = BatchInferenceEngine(agent, batch_size=4)
        
        assert batch_engine.batch_size == 4
        assert batch_engine.agent is agent
        assert batch_engine.pending_observations == []
    
    def test_batch_processing(self, tmp_path, sample_prices):
        """Test batch processing."""
        price_data = {s: [p] * 10 for s, p in sample_prices.items()}
        
        env = MultiSymbolTradingEnv(
            symbols=list(sample_prices.keys()),
            price_data=price_data,
        )
        
        config = TrainerConfig(total_timesteps=100, verbose=0)
        trainer = PPOTrainer(env, config)
        trainer.train(total_timesteps=100)
        
        model_path = str(tmp_path / "test_model.zip")
        trainer.save(model_path)
        
        agent = RLTradingAgent(
            model_path=model_path,
            symbols=list(sample_prices.keys()),
        )
        
        batch_engine = BatchInferenceEngine(agent, batch_size=2)
        
        # Add observations
        obs_shape = env.observation_space.shape
        batch_engine.add_observation("BTCUSDT", np.zeros(obs_shape, dtype=np.float32))
        batch_engine.add_observation("ETHUSDT", np.zeros(obs_shape, dtype=np.float32))
        
        assert len(batch_engine.pending_observations) == 2
        
        # Process batch
        results = batch_engine.process_batch(deterministic=True)
        
        assert isinstance(results, dict)


# ============================================================================
# Integration with Task 9-10
# ============================================================================

class TestAnomalyIntegration:
    """Test integration with anomaly detection (Task 9)."""
    
    def test_process_action_with_anomaly(self, tmp_path, sample_prices, mock_anomaly_detector):
        """Test action processing with anomaly flags."""
        price_data = {s: [p] * 10 for s, p in sample_prices.items()}
        
        env = MultiSymbolTradingEnv(
            symbols=list(sample_prices.keys()),
            price_data=price_data,
        )
        
        config = TrainerConfig(total_timesteps=100, verbose=0)
        trainer = PPOTrainer(env, config)
        trainer.train(total_timesteps=100)
        
        model_path = str(tmp_path / "test_model.zip")
        trainer.save(model_path)
        
        agent = RLTradingAgent(
            model_path=model_path,
            symbols=list(sample_prices.keys()),
            anomaly_detector=mock_anomaly_detector,
        )
        
        # Set anomaly flag for one symbol
        anomaly_flags = {"BTCUSDT": True, "ETHUSDT": False, "XRPUSDT": False}
        
        action = np.array([0.5, 0.5, 0.5], dtype=np.float32)
        result = agent.process_action(action, sample_prices, anomaly_flags)
        
        assert "trades" in result


class TestRegimeIntegration:
    """Test integration with regime detection (Task 10)."""
    
    def test_process_action_with_regime(self, tmp_path, sample_prices, mock_regime_detector):
        """Test action processing with regime awareness."""
        price_data = {s: [p] * 10 for s, p in sample_prices.items()}
        
        env = MultiSymbolTradingEnv(
            symbols=list(sample_prices.keys()),
            price_data=price_data,
        )
        
        config = TrainerConfig(total_timesteps=100, verbose=0)
        trainer = PPOTrainer(env, config)
        trainer.train(total_timesteps=100)
        
        model_path = str(tmp_path / "test_model.zip")
        trainer.save(model_path)
        
        agent = RLTradingAgent(
            model_path=model_path,
            symbols=list(sample_prices.keys()),
            regime_detector=mock_regime_detector,
        )
        
        regime_state = {"BTCUSDT": "bull", "ETHUSDT": "sideways", "XRPUSDT": "bear"}
        
        action = np.array([0.5, 0.5, 0.5], dtype=np.float32)
        result = agent.process_action(action, sample_prices, regime_state=regime_state)
        
        assert "trades" in result


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
