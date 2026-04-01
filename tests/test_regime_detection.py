"""
Comprehensive tests for HMM-based regime detection system.
Focused on Indonesian IDX context (Bursa Efek Indonesia).

Tests cover:
1. HMM training on market regimes
2. Regime classification
3. Probability estimation
4. Strategy parameter adjustment
5. Integration with trading system
"""

import pytest
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from ml.regime_detector import (
    RegimeType,
    RegimeState,
    HMMRegimeDetector,
    RegimeAnalyzer,
    RegimeIntegration,
    HMM_AVAILABLE
)


# ============================================================================
# Test Data Generation (Indonesian market context)
# ============================================================================

@pytest.fixture
def bull_market_data():
    """Generate simulated bull market data (uptrend)."""
    np.random.seed(42)
    n_samples = 200
    
    # Bull market: positive drift, moderate volatility
    returns = np.random.normal(loc=0.002, scale=0.01, size=n_samples)  # +0.2% daily
    volatility = np.random.uniform(0.008, 0.015, n_samples)
    volume = np.random.uniform(1e7, 3e7, n_samples)  # IDX volume
    direction = np.ones(n_samples)  # Uptrend
    
    features = pd.DataFrame({
        'returns': returns,
        'volatility': volatility,
        'volume': volume,
        'direction': direction
    })
    
    # Generate prices from returns
    prices = 5000 * np.exp(np.cumsum(returns))
    
    return features, prices, volume


@pytest.fixture
def bear_market_data():
    """Generate simulated bear market data (downtrend)."""
    np.random.seed(43)
    n_samples = 200
    
    # Bear market: negative drift, higher volatility
    returns = np.random.normal(loc=-0.001, scale=0.015, size=n_samples)  # -0.1% daily
    volatility = np.random.uniform(0.015, 0.025, n_samples)
    volume = np.random.uniform(1e7, 3e7, n_samples)
    direction = -np.ones(n_samples)  # Downtrend
    
    features = pd.DataFrame({
        'returns': returns,
        'volatility': volatility,
        'volume': volume,
        'direction': direction
    })
    
    prices = 5000 * np.exp(np.cumsum(returns))
    return features, prices, volume


@pytest.fixture
def sideways_market_data():
    """Generate simulated sideways (ranging) market data."""
    np.random.seed(44)
    n_samples = 200
    
    # Sideways: near-zero drift, low volatility
    returns = np.random.normal(loc=0.0, scale=0.008, size=n_samples)
    volatility = np.random.uniform(0.005, 0.012, n_samples)
    volume = np.random.uniform(0.8e7, 2e7, n_samples)
    direction = np.zeros(n_samples)  # Range-bound
    
    features = pd.DataFrame({
        'returns': returns,
        'volatility': volatility,
        'volume': volume,
        'direction': direction
    })
    
    prices = 5000 * np.exp(np.cumsum(returns))
    return features, prices, volume


@pytest.fixture
def mixed_market_data(bull_market_data, bear_market_data, sideways_market_data):
    """Combine all three regimes for realistic HMM training."""
    bull_f, bull_p, bull_v = bull_market_data
    bear_f, bear_p, bear_v = bear_market_data
    sideways_f, sideways_p, sideways_v = sideways_market_data
    
    # Concatenate in sequence
    features = pd.concat([bull_f, sideways_f, bear_f], ignore_index=True)
    prices = np.concatenate([bull_p, sideways_p, bear_p])
    volumes = np.concatenate([bull_v, sideways_v, bear_v])
    
    return features, prices, volumes


# ============================================================================
# Regime Type Tests
# ============================================================================

class TestRegimeType:
    """Test RegimeType enum and strategy parameters."""
    
    def test_regime_labels(self):
        """Test regime type labels."""
        assert RegimeType.BULL.to_label() == 'BULL'
        assert RegimeType.BEAR.to_label() == 'BEAR'
        assert RegimeType.SIDEWAYS.to_label() == 'SIDEWAYS'
    
    def test_bull_params(self):
        """Test BULL regime parameters."""
        params = RegimeType.BULL.get_strategy_params()
        assert params['risk_multiplier'] == 1.0
        assert params['position_size_ratio'] == 1.0
        assert params['take_profit_percent'] == 0.06
    
    def test_bear_params(self):
        """Test BEAR regime parameters."""
        params = RegimeType.BEAR.get_strategy_params()
        assert params['risk_multiplier'] == 0.5
        assert params['position_size_ratio'] == 0.5
        assert params['stop_loss_percent'] == 0.02
    
    def test_sideways_params(self):
        """Test SIDEWAYS regime parameters."""
        params = RegimeType.SIDEWAYS.get_strategy_params()
        assert params['risk_multiplier'] == 0.7
        assert params['position_size_ratio'] == 0.7


# ============================================================================
# Regime State Tests
# ============================================================================

class TestRegimeState:
    """Test RegimeState data structure."""
    
    def test_creation(self):
        """Test creating regime state."""
        state = RegimeState(
            regime=RegimeType.BULL,
            probability=0.95,
            timestamp=datetime.now().isoformat(),
            features={'price': 5000, 'return': 0.002}
        )
        
        assert state.regime == RegimeType.BULL
        assert state.probability == 0.95
    
    def test_to_dict(self):
        """Test converting to dictionary."""
        state = RegimeState(
            regime=RegimeType.BULL,
            probability=0.85,
            timestamp=datetime.now().isoformat(),
            features={'price': 5000}
        )
        
        d = state.to_dict()
        assert d['regime'] == 'BULL'
        assert d['probability'] == 0.85
        assert 'strategy_params' in d


# ============================================================================
# HMM Detector Tests
# ============================================================================

@pytest.mark.skipif(not HMM_AVAILABLE, reason="hmmlearn not available")
class TestHMMRegimeDetector:
    """Test HMM-based regime detector."""
    
    def test_initialization(self):
        """Test detector initialization."""
        detector = HMMRegimeDetector(n_states=3)
        assert detector.n_states == 3
        assert not detector.is_fitted
    
    def test_fit(self, mixed_market_data):
        """Test fitting HMM on mixed market data."""
        features, prices, volumes = mixed_market_data
        
        detector = HMMRegimeDetector(n_states=3, n_iter=100)
        detector.fit(features)
        
        assert detector.is_fitted
        assert detector.means is not None
        assert len(detector.state_mapping) == 3
    
    def test_predict(self, mixed_market_data):
        """Test regime prediction."""
        features, prices, volumes = mixed_market_data
        
        detector = HMMRegimeDetector(n_states=3)
        detector.fit(features.iloc[:400])
        
        predictions = detector.predict(features.iloc[400:])
        assert len(predictions) == len(features.iloc[400:])
        assert all(p in [0, 1, 2] for p in predictions)
    
    def test_predict_proba(self, mixed_market_data):
        """Test probability estimation."""
        features, prices, volumes = mixed_market_data
        
        detector = HMMRegimeDetector(n_states=3)
        detector.fit(features.iloc[:400])
        
        proba = detector.predict_proba(features.iloc[400:])
        
        assert proba.shape[0] == len(features.iloc[400:])
        assert proba.shape[1] == 3
        # Probabilities should sum to 1
        np.testing.assert_array_almost_equal(proba.sum(axis=1), np.ones(len(proba)))
    
    def test_regime_mapping(self, bull_market_data, bear_market_data):
        """Test that regimes map to correct types."""
        bull_f, bull_p, bull_v = bull_market_data
        bear_f, bear_p, bear_v = bear_market_data
        
        detector = HMMRegimeDetector(n_states=3)
        combined = pd.concat([bull_f, bear_f], ignore_index=True)
        detector.fit(combined)
        
        # Predict on each
        bull_pred = detector.predict(bull_f)
        bear_pred = detector.predict(bear_f)
        
        # Most bull samples should be in bull state
        bull_regime_types = [detector.get_regime_type(p) for p in bull_pred]
        bull_count = sum(1 for r in bull_regime_types if r == RegimeType.BULL)
        
        assert bull_count > 0  # Should detect some bull regime


# ============================================================================
# Regime Analyzer Tests
# ============================================================================

@pytest.mark.skipif(not HMM_AVAILABLE, reason="hmmlearn not available")
class TestRegimeAnalyzer:
    """Test regime analysis and statistics."""
    
    def test_analyze_regimes(self, mixed_market_data):
        """Test regime statistics analysis."""
        features, prices, volumes = mixed_market_data
        
        detector = HMMRegimeDetector(n_states=3)
        detector.fit(features)
        
        states = detector.predict(features)
        
        analyzer = RegimeAnalyzer()
        stats = analyzer.analyze_regimes(prices, volumes, states, detector)
        
        # Should have stats for each regime
        assert len(stats) <= 3
        
        # Check stats contain expected fields
        for regime, regime_stats in stats.items():
            assert 'mean_return' in regime_stats
            assert 'std_return' in regime_stats
            assert 'frequency_percent' in regime_stats


# ============================================================================
# Regime Integration Tests
# ============================================================================

@pytest.mark.skipif(not HMM_AVAILABLE, reason="hmmlearn not available")
class TestRegimeIntegration:
    """Test integration with trading system."""
    
    def test_update_regime(self, mixed_market_data):
        """Test regime update."""
        features, prices, volumes = mixed_market_data
        
        detector = HMMRegimeDetector(n_states=3)
        detector.fit(features)
        
        integration = RegimeIntegration(detector)
        
        # Update with sample
        new_regime = integration.update_regime(
            features.iloc[400:401],
            current_price=prices[400]
        )
        
        assert isinstance(new_regime, RegimeState)
        assert new_regime.regime in [RegimeType.BULL, RegimeType.BEAR, RegimeType.SIDEWAYS]
    
    def test_get_strategy_params(self, mixed_market_data):
        """Test getting strategy parameters."""
        features, prices, volumes = mixed_market_data
        
        detector = HMMRegimeDetector(n_states=3)
        detector.fit(features)
        
        integration = RegimeIntegration(detector)
        integration.update_regime(features.iloc[400:401], prices[400])
        
        params = integration.get_strategy_params()
        
        assert 'risk_multiplier' in params
        assert 'position_size_ratio' in params
        assert 'stop_loss_percent' in params
    
    def test_should_trade(self, mixed_market_data):
        """Test trade signal based on regime confidence."""
        features, prices, volumes = mixed_market_data
        
        detector = HMMRegimeDetector(n_states=3)
        detector.fit(features)
        
        integration = RegimeIntegration(detector)
        integration.update_regime(features.iloc[400:401], prices[400])
        
        # Should be able to trade (confidence threshold)
        can_trade = integration.should_trade()
        assert isinstance(can_trade, bool)
    
    def test_adjust_position_for_regime(self, mixed_market_data):
        """Test position sizing adjustment by regime."""
        features, prices, volumes = mixed_market_data
        
        detector = HMMRegimeDetector(n_states=3)
        detector.fit(features)
        
        integration = RegimeIntegration(detector)
        integration.update_regime(features.iloc[400:401], prices[400])
        
        # Test position adjustment
        base_pos = 10000
        
        # Bull
        bull_adj = integration.adjust_position_for_regime(base_pos, RegimeType.BULL)
        assert bull_adj == base_pos  # 1.0 multiplier
        
        # Bear
        bear_adj = integration.adjust_position_for_regime(base_pos, RegimeType.BEAR)
        assert bear_adj == base_pos * 0.5  # 0.5 multiplier
        
        # Sideways
        sideways_adj = integration.adjust_position_for_regime(base_pos, RegimeType.SIDEWAYS)
        assert sideways_adj == base_pos * 0.7  # 0.7 multiplier
    
    def test_idx_lot_size_compliance(self, mixed_market_data):
        """Test IDX minimum lot size compliance (100 shares)."""
        features, prices, volumes = mixed_market_data
        
        detector = HMMRegimeDetector(n_states=3)
        detector.fit(features)
        
        integration = RegimeIntegration(detector)
        integration.update_regime(features.iloc[400:401], prices[400])
        
        # Test with small position
        small_pos = 50  # Below 1 lot (100 shares)
        adjusted = integration.adjust_position_for_regime(small_pos, RegimeType.BULL)
        
        assert adjusted == 0 or adjusted >= 100  # Either 0 or at least 1 lot


# ============================================================================
# Integration Tests
# ============================================================================

@pytest.mark.skipif(not HMM_AVAILABLE, reason="hmmlearn not available")
class TestRegimeDetectionIntegration:
    """End-to-end integration tests."""
    
    def test_full_workflow(self, mixed_market_data):
        """Test complete workflow: fit -> predict -> integrate."""
        features, prices, volumes = mixed_market_data
        
        # Split data
        train_features = features.iloc[:400]
        test_features = features.iloc[400:]
        test_prices = prices[400:]
        
        # 1. Train detector
        detector = HMMRegimeDetector(n_states=3)
        detector.fit(train_features)
        
        # 2. Predict
        states = detector.predict(test_features)
        assert len(states) == len(test_features)
        
        # 3. Integrate
        integration = RegimeIntegration(detector)
        
        # 4. Process each sample
        for i in range(min(10, len(test_features))):
            regime = integration.update_regime(
                test_features.iloc[i:i+1],
                current_price=test_prices[i]
            )
            
            assert regime.regime in [RegimeType.BULL, RegimeType.BEAR, RegimeType.SIDEWAYS]
            
            # Get params for current regime
            params = integration.get_strategy_params()
            assert params['risk_multiplier'] > 0
    
    def test_regime_transitions(self, mixed_market_data):
        """Test regime transition tracking."""
        features, prices, volumes = mixed_market_data
        
        detector = HMMRegimeDetector(n_states=3)
        detector.fit(features.iloc[:400])
        
        integration = RegimeIntegration(detector)
        
        # Process all samples
        for i in range(len(features)):
            integration.update_regime(features.iloc[i:i+1], prices[i])
        
        # Check transitions were tracked
        assert isinstance(integration.regime_transitions, list)
        
        # Get status
        status = integration.get_regime_status()
        assert 'regime' in status
        assert 'confidence' in status
        assert 'transitions' in status


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
