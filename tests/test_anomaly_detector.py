"""Tests for Anomaly Detection Module"""
import unittest
import numpy as np
import pandas as pd
import tempfile
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

try:
    from src.ml.anomaly_detector import (
        IsolationForestDetector,
        StatisticalAnomalyDetector,
        AnomalyRiskManager,
        SKLEARN_AVAILABLE
    )
except ImportError:
    SKLEARN_AVAILABLE = False


@unittest.skipIf(not SKLEARN_AVAILABLE, "scikit-learn not installed")
class TestIsolationForestDetector(unittest.TestCase):
    def setUp(self):
        self.detector = IsolationForestDetector(contamination=0.1)
        np.random.seed(42)
    
    def test_fit_predict(self):
        X = pd.DataFrame(np.random.randn(200, 5))
        self.detector.fit(X)
        
        predictions = self.detector.predict(X[:10])
        self.assertEqual(len(predictions), 10)
        self.assertTrue(all(p in [1, -1] for p in predictions))
    
    def test_score_samples(self):
        X = pd.DataFrame(np.random.randn(200, 5))
        self.detector.fit(X)
        
        scores = self.detector.score_samples(X[:10])
        self.assertEqual(len(scores), 10)
        self.assertTrue(np.isfinite(scores).all())


@unittest.skipIf(not SKLEARN_AVAILABLE, "scikit-learn not installed")
class TestStatisticalAnomalyDetector(unittest.TestCase):
    def setUp(self):
        self.detector = StatisticalAnomalyDetector(window=50, z_threshold=3.0)
        np.random.seed(42)
    
    def test_price_anomaly_detection(self):
        prices = 100 * np.exp(np.cumsum(np.random.randn(200) * 0.01))
        prices[150] = prices[149] * 1.2  # 20% spike
        
        anomalies, z_scores = self.detector.detect_price_anomaly(prices)
        
        self.assertEqual(len(anomalies), len(prices))
        self.assertTrue(anomalies[150])  # Should detect spike
    
    def test_volume_anomaly_detection(self):
        volumes = np.random.uniform(1e6, 2e6, 200)
        volumes[150] = volumes[149] * 10  # 10x spike
        
        anomalies, ratios = self.detector.detect_volume_anomaly(volumes)
        
        self.assertEqual(len(anomalies), len(volumes))
        self.assertTrue(anomalies[150])  # Should detect spike


@unittest.skipIf(not SKLEARN_AVAILABLE, "scikit-learn not installed")
class TestAnomalyRiskManager(unittest.TestCase):
    def setUp(self):
        self.risk_mgr = AnomalyRiskManager(risk_reduction_factor=0.5)
        np.random.seed(42)
    
    def test_position_adjustment(self):
        base_position = 10000
        
        # Normal case
        adjusted = self.risk_mgr.adjust_position_size(base_position, {'is_anomaly': False})
        self.assertEqual(adjusted, base_position)
        
        # Anomaly case
        anomaly_result = {
            'is_anomaly': True,
            'risk_multiplier': 0.5,
            'anomaly_types': ['price_spike']
        }
        adjusted = self.risk_mgr.adjust_position_size(base_position, anomaly_result)
        self.assertEqual(adjusted, base_position * 0.5)


if __name__ == '__main__':
    unittest.main(verbosity=2)
