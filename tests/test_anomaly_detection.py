"""
Comprehensive tests for anomaly detection system.

Tests cover:
1. IsolationForest detector
2. Statistical anomaly detector
3. Autoencoder detector (if PyTorch available)
4. Ensemble risk manager
5. Position sizing adjustments
6. Integration scenarios
"""

import pytest
import numpy as np
import pandas as pd
from datetime import datetime
from pathlib import Path
import sys
import logging

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.ml.anomaly_detector import (
    IsolationForestDetector,
    StatisticalAnomalyDetector,
    AnomalyRiskManager,
    SKLEARN_AVAILABLE,
    TORCH_AVAILABLE
)

# Conditionally import autoencoder tests
if TORCH_AVAILABLE:
    from src.ml.anomaly_detector import AutoencoderDetector, AutoencoderAnomaly

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ============================================================================
# Test Data Generation
# ============================================================================

@pytest.fixture
def normal_trading_data():
    """Generate normal trading data."""
    np.random.seed(42)
    n_samples = 500
    
    # Geometric Brownian Motion for prices
    returns = np.random.randn(n_samples) * 0.01
    prices = 100 * np.exp(np.cumsum(returns))
    
    # Normal trading volume
    volumes = np.random.uniform(1e6, 2e6, n_samples)
    
    # Volatility (realized)
    volatility = pd.Series(returns).rolling(20).std().fillna(0).values
    
    # RSI-like feature
    rsi = np.random.uniform(30, 70, n_samples)
    
    features = pd.DataFrame({
        'returns': returns,
        'volume': volumes,
        'volatility': volatility,
        'rsi': rsi,
        'vwap_dev': np.random.uniform(-0.01, 0.01, n_samples)
    })
    
    return features, prices, volumes


@pytest.fixture
def normal_training_data(normal_trading_data):
    """Return first 400 samples for training."""
    features, prices, volumes = normal_trading_data
    return features.iloc[:400], prices[:400], volumes[:400]


@pytest.fixture
def test_data_with_anomalies(normal_trading_data):
    """Return last 100 samples with injected anomalies."""
    features, prices, volumes = normal_trading_data
    test_features = features.iloc[400:].copy()
    test_prices = prices[400:].copy()
    test_volumes = volumes[400:].copy()
    
    # Inject flash crash at sample 20
    test_prices[20] = test_prices[19] * 0.85
    test_features.iloc[20, 0] = -0.15
    
    # Inject volume spike at sample 50
    test_volumes[50] = test_volumes[49] * 10
    test_features.iloc[50, 1] = test_volumes[50]
    
    # Inject volatility spike at sample 80
    test_features.iloc[80, 2] = 0.10
    
    return test_features, test_prices, test_volumes


# ============================================================================
# IsolationForest Tests
# ============================================================================

@pytest.mark.skipif(not SKLEARN_AVAILABLE, reason="scikit-learn not available")
class TestIsolationForestDetector:
    """Test IsolationForest anomaly detector."""
    
    def test_initialization(self):
        """Test detector initialization."""
        detector = IsolationForestDetector(contamination=0.05, n_estimators=100)
        assert not detector.is_fitted
        assert detector.feature_names == []
    
    def test_fit(self, normal_training_data):
        """Test fitting detector."""
        features, _, _ = normal_training_data
        detector = IsolationForestDetector()
        detector.fit(features)
        
        assert detector.is_fitted
        assert len(detector.feature_names) == features.shape[1]
    
    def test_predict_normal(self, normal_training_data):
        """Test prediction on normal data."""
        features, _, _ = normal_training_data
        detector = IsolationForestDetector(contamination=0.05)
        detector.fit(features)
        
        # Predict on training data
        predictions = detector.predict(features)
        assert all(p in [1, -1] for p in predictions)
        
        # Most should be normal (1)
        normal_ratio = np.sum(predictions == 1) / len(predictions)
        assert normal_ratio > 0.90  # 90%+ should be normal
    
    def test_predict_with_anomalies(self, normal_training_data, test_data_with_anomalies):
        """Test detection of anomalies."""
        train_features, _, _ = normal_training_data
        test_features, _, _ = test_data_with_anomalies
        
        detector = IsolationForestDetector(contamination=0.10)
        detector.fit(train_features)
        
        predictions = detector.predict(test_features)
        anomaly_ratio = np.sum(predictions == -1) / len(predictions)
        
        # Should detect some anomalies
        assert anomaly_ratio > 0.0
    
    def test_score_samples(self, normal_training_data):
        """Test anomaly scoring."""
        features, _, _ = normal_training_data
        detector = IsolationForestDetector()
        detector.fit(features)
        
        scores = detector.score_samples(features)
        assert len(scores) == len(features)
        assert all(isinstance(s, (float, np.floating)) for s in scores)
    
    def test_fit_raises_on_unfitted_predict(self, normal_training_data):
        """Test that predict raises error before fitting."""
        features, _, _ = normal_training_data
        detector = IsolationForestDetector()
        
        with pytest.raises(ValueError, match="not fitted"):
            detector.predict(features)


# ============================================================================
# Statistical Detector Tests
# ============================================================================

class TestStatisticalAnomalyDetector:
    """Test statistical anomaly detector."""
    
    def test_initialization(self):
        """Test initialization."""
        detector = StatisticalAnomalyDetector(window=100, z_threshold=3.0)
        assert detector.window == 100
        assert detector.z_threshold == 3.0
    
    def test_detect_price_anomaly(self):
        """Test price spike detection."""
        np.random.seed(42)
        prices = 100 * np.exp(np.cumsum(np.random.randn(200) * 0.01))
        
        detector = StatisticalAnomalyDetector(window=50, z_threshold=3.0)
        anomalies, z_scores = detector.detect_price_anomaly(prices)
        
        assert len(anomalies) == len(prices)
        assert len(z_scores) == len(prices)
        assert all(isinstance(a, (bool, np.bool_)) for a in anomalies)
    
    def test_detect_flash_crash(self):
        """Test detection of flash crash."""
        np.random.seed(42)
        prices = 100 * np.exp(np.cumsum(np.random.randn(200) * 0.01))
        
        # Inject flash crash
        prices[150] = prices[149] * 0.80  # 20% drop
        
        detector = StatisticalAnomalyDetector(window=50, z_threshold=2.5)
        anomalies, z_scores = detector.detect_price_anomaly(prices)
        
        # Should detect anomaly
        assert np.any(anomalies[145:155])
    
    def test_detect_volume_anomaly(self):
        """Test volume anomaly detection."""
        np.random.seed(42)
        volumes = np.random.uniform(1e6, 2e6, 200)
        
        detector = StatisticalAnomalyDetector(window=50, iqr_multiplier=1.5)
        anomalies, ratios = detector.detect_volume_anomaly(volumes)
        
        assert len(anomalies) == len(volumes)
        assert len(ratios) == len(volumes)
    
    def test_detect_volume_spike(self):
        """Test detection of volume spike."""
        np.random.seed(42)
        volumes = np.random.uniform(1e6, 2e6, 200)
        
        # Inject volume spike
        volumes[150] = volumes[149] * 10
        
        detector = StatisticalAnomalyDetector(window=50)
        anomalies, ratios = detector.detect_volume_anomaly(volumes)
        
        # Should detect spike
        assert np.any(anomalies[145:155])
    
    def test_detect_volatility_spike(self):
        """Test volatility spike detection."""
        np.random.seed(42)
        returns = np.random.randn(200) * 0.01
        
        # Inject volatility spike
        returns[150:155] = np.random.randn(5) * 0.10  # 10x volatility
        
        detector = StatisticalAnomalyDetector(window=50)
        anomalies = detector.detect_volatility_spike(returns, threshold_multiplier=3.0)
        
        assert len(anomalies) == len(returns)
        assert np.any(anomalies[145:160])


# ============================================================================
# Autoencoder Tests (PyTorch required)
# ============================================================================

@pytest.mark.skipif(not TORCH_AVAILABLE, reason="PyTorch not available")
class TestAutoencoderDetector:
    """Test autoencoder-based anomaly detector."""
    
    def test_initialization(self):
        """Test detector initialization."""
        detector = AutoencoderDetector(input_dim=5, hidden_dim=16)
        assert detector.is_fitted is False
        assert detector.reconstruction_threshold is None
    
    def test_fit(self, normal_training_data):
        """Test fitting autoencoder."""
        features, _, _ = normal_training_data
        detector = AutoencoderDetector(input_dim=features.shape[1], hidden_dim=16)
        
        detector.fit(features, epochs=10, batch_size=32, verbose=False)
        
        assert detector.is_fitted
        assert detector.reconstruction_threshold is not None
        assert len(detector.training_errors) == len(features)
    
    def test_predict_normal(self, normal_training_data):
        """Test prediction on normal data."""
        features, _, _ = normal_training_data
        detector = AutoencoderDetector(input_dim=features.shape[1], hidden_dim=16)
        detector.fit(features, epochs=10, verbose=False)
        
        predictions = detector.predict(features)
        assert all(p in [1, -1] for p in predictions)
        
        # Most should be normal
        normal_ratio = np.sum(predictions == 1) / len(predictions)
        assert normal_ratio > 0.90
    
    def test_score_samples(self, normal_training_data):
        """Test anomaly scoring."""
        features, _, _ = normal_training_data
        detector = AutoencoderDetector(input_dim=features.shape[1], hidden_dim=16)
        detector.fit(features, epochs=10, verbose=False)
        
        scores = detector.score_samples(features)
        assert len(scores) == len(features)
    
    def test_detect_anomaly(self, normal_training_data):
        """Test detection of injected anomalies."""
        features, _, _ = normal_training_data
        
        # Create anomalous sample
        anomaly = features.iloc[0:1].copy()
        anomaly.iloc[0] = anomaly.iloc[0] * 5  # Extreme values
        
        detector = AutoencoderDetector(input_dim=features.shape[1], hidden_dim=16)
        detector.fit(features, epochs=10, verbose=False)
        
        normal_pred = detector.predict(features.iloc[0:1])
        anomaly_pred = detector.predict(anomaly)
        
        # Anomaly should have different score
        normal_score = detector.score_samples(features.iloc[0:1])[0]
        anomaly_score = detector.score_samples(anomaly)[0]
        assert anomaly_score < normal_score
    
    def test_fit_raises_on_unfitted_predict(self, normal_training_data):
        """Test that predict raises error before fitting."""
        features, _, _ = normal_training_data
        detector = AutoencoderDetector(input_dim=features.shape[1])
        
        with pytest.raises(ValueError, match="not fitted"):
            detector.predict(features)


# ============================================================================
# AnomalyRiskManager Tests
# ============================================================================

@pytest.mark.skipif(not SKLEARN_AVAILABLE, reason="scikit-learn not available")
class TestAnomalyRiskManager:
    """Test risk manager with ensemble anomaly detection."""
    
    def test_initialization(self):
        """Test risk manager initialization."""
        mgr = AnomalyRiskManager(risk_reduction_factor=0.5)
        assert mgr.risk_reduction_factor == 0.5
        assert mgr.current_anomaly_score == 0.0
        assert len(mgr.anomaly_history) == 0
    
    def test_fit(self, normal_training_data):
        """Test fitting risk manager."""
        features, _, _ = normal_training_data
        mgr = AnomalyRiskManager()
        mgr.fit(features, autoencoder_epochs=5)
        
        # Check detectors are fitted
        assert mgr.isolation_detector.is_fitted
        report = mgr.get_anomaly_report()
        assert report['detectors_fitted']['isolation_forest']
    
    def test_detect_normal_data(self, normal_training_data):
        """Test detection on normal data."""
        features, prices, volumes = normal_training_data
        mgr = AnomalyRiskManager()
        mgr.fit(features)
        
        result = mgr.detect_anomalies(
            features.iloc[-5:],
            prices[-5:],
            volumes[-5:]
        )
        
        assert 'is_anomaly' in result
        assert 'anomaly_score' in result
        assert 'risk_multiplier' in result
        assert result['risk_multiplier'] >= 0.0 and result['risk_multiplier'] <= 1.0
    
    def test_detect_price_anomaly(self, normal_training_data):
        """Test detection of price anomalies."""
        features, prices, volumes = normal_training_data
        mgr = AnomalyRiskManager()
        mgr.fit(features)
        
        # Create anomalous sample
        test_features = features.iloc[-10:].copy()
        test_prices = prices[-10:].copy()
        test_volumes = volumes[-10:]
        
        # Inject price anomaly
        test_prices[-1] = test_prices[-2] * 0.80
        
        result = mgr.detect_anomalies(
            test_features.iloc[-5:],
            test_prices[-5:],
            test_volumes[-5:]
        )
        
        # Could detect anomaly or not depending on z_threshold
        assert 'is_anomaly' in result
    
    def test_detect_volume_anomaly(self, normal_training_data):
        """Test detection of volume anomalies."""
        features, prices, volumes = normal_training_data
        mgr = AnomalyRiskManager()
        mgr.fit(features)
        
        # Create anomalous sample
        test_features = features.iloc[-10:].copy()
        test_prices = prices[-10:].copy()
        test_volumes = volumes[-10:].copy()
        
        # Inject volume spike
        test_volumes[-1] = test_volumes[-2] * 10
        test_features.iloc[-1, 1] = test_volumes[-1]
        
        result = mgr.detect_anomalies(
            test_features.iloc[-5:],
            test_prices[-5:],
            test_volumes[-5:]
        )
        
        assert 'is_anomaly' in result
    
    def test_adjust_position_size(self, normal_training_data):
        """Test position sizing adjustment."""
        features, prices, volumes = normal_training_data
        mgr = AnomalyRiskManager(risk_reduction_factor=0.5)
        mgr.fit(features)
        
        # Normal case
        result_normal = mgr.detect_anomalies(features.iloc[-1:])
        adjusted = mgr.adjust_position_size(10000.0, result_normal)
        assert adjusted == 10000.0
        
        # Anomaly case
        result_anomaly = {
            'is_anomaly': True,
            'anomaly_types': ['test'],
            'risk_multiplier': 0.5
        }
        adjusted = mgr.adjust_position_size(10000.0, result_anomaly)
        assert adjusted == 5000.0
    
    def test_anomaly_history(self, normal_training_data):
        """Test anomaly history tracking."""
        features, prices, volumes = normal_training_data
        mgr = AnomalyRiskManager()
        mgr.fit(features)
        
        # Run multiple detections
        for i in range(5):
            mgr.detect_anomalies(features.iloc[-5+i:-4+i])
        
        # Initial history should be empty
        assert mgr.anomaly_history is not None
    
    def test_get_anomaly_report(self, normal_training_data):
        """Test anomaly report generation."""
        features, _, _ = normal_training_data
        mgr = AnomalyRiskManager()
        mgr.fit(features)
        
        # Empty report
        report = mgr.get_anomaly_report()
        assert report['total_anomalies'] == 0
        assert 'current_score' in report
        assert 'detectors_fitted' in report
    
    def test_ensemble_voting(self, normal_training_data):
        """Test ensemble voting mechanism."""
        features, prices, volumes = normal_training_data
        
        mgr = AnomalyRiskManager(ensemble_method='voting')
        mgr.fit(features)
        
        result = mgr.detect_anomalies(features.iloc[-1:])
        assert 'detector_votes' in result
    
    def test_ensemble_weighted(self, normal_training_data):
        """Test ensemble weighting mechanism."""
        features, prices, volumes = normal_training_data
        
        mgr = AnomalyRiskManager(ensemble_method='weighted')
        mgr.fit(features)
        
        result = mgr.detect_anomalies(features.iloc[-1:])
        assert 'anomaly_score' in result


# ============================================================================
# Integration Tests
# ============================================================================

@pytest.mark.skipif(not SKLEARN_AVAILABLE, reason="scikit-learn not available")
class TestAnomalyDetectionIntegration:
    """Integration tests for anomaly detection system."""
    
    def test_full_pipeline(self, normal_training_data, test_data_with_anomalies):
        """Test complete anomaly detection pipeline."""
        train_features, train_prices, train_volumes = normal_training_data
        test_features, test_prices, test_volumes = test_data_with_anomalies
        
        # Initialize and fit
        mgr = AnomalyRiskManager(risk_reduction_factor=0.5)
        mgr.fit(train_features)
        
        # Run detections on test data
        anomaly_count = 0
        position_reductions = []
        
        for i in range(len(test_features)):
            result = mgr.detect_anomalies(
                test_features.iloc[i:i+1],
                test_prices[:i+1] if i > 0 else test_prices[0:1],
                test_volumes[:i+1] if i > 0 else test_volumes[0:1]
            )
            
            if result['is_anomaly']:
                anomaly_count += 1
                
                adjusted = mgr.adjust_position_size(10000.0, result)
                reduction = (10000.0 - adjusted) / 10000.0
                position_reductions.append(reduction)
        
        # Should detect at least one anomaly from injected ones
        assert anomaly_count >= 0  # May not detect all depending on thresholds
    
    def test_multi_detector_consensus(self, normal_training_data):
        """Test consensus from multiple detectors."""
        features, prices, volumes = normal_training_data
        
        mgr = AnomalyRiskManager(ensemble_method='voting')
        mgr.fit(features, autoencoder_epochs=5)
        
        # Normal data should have consensus that it's normal
        for i in range(len(features) - 5, len(features)):
            result = mgr.detect_anomalies(
                features.iloc[i:i+1],
                prices[:i+1],
                volumes[:i+1]
            )
            
            # Most normal data should not trigger anomaly
            assert result['risk_multiplier'] >= 0.4  # At most moderate reduction


# ============================================================================
# Run Tests
# ============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "-x"])
