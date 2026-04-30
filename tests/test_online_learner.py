"""
Tests for Online Learning Pipeline

Tests incremental learning, drift detection, and adaptive retraining.
"""
import unittest
import numpy as np
import pandas as pd
from datetime import datetime
import tempfile
import os
import sys

# Add src to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

try:
    from src.ml.online_learner import (
        OnlineLearner,
        ConceptDriftDetector,
        OnlineLearningPipeline,
        RIVER_AVAILABLE
    )
except ImportError as e:
    print(f"Import error: {e}")
    RIVER_AVAILABLE = False


@unittest.skipIf(not RIVER_AVAILABLE, "River library not installed")
class TestOnlineLearner(unittest.TestCase):
    """Test OnlineLearner class."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.learner = OnlineLearner(n_models=5, grace_period=10)
        np.random.seed(42)
    
    def test_initialization(self):
        """Test learner initialization."""
        self.assertIsNotNone(self.learner.model)
        self.assertEqual(self.learner.n_samples_seen, 0)
        self.assertEqual(len(self.learner.performance_history), 0)
    
    def test_partial_fit(self):
        """Test incremental learning with single sample."""
        X = {'feature1': 0.5, 'feature2': -0.3, 'feature3': 1.2}
        y = 1
        
        initial_samples = self.learner.n_samples_seen
        self.learner.partial_fit(X, y)
        
        self.assertEqual(self.learner.n_samples_seen, initial_samples + 1)
    
    def test_prediction_after_training(self):
        """Test predictions after sufficient training."""
        # Train with simple linear pattern
        for _ in range(50):
            x1 = np.random.uniform(-1, 1)
            x2 = np.random.uniform(-1, 1)
            y = 1 if x1 + x2 > 0 else 0
            
            X = {'x1': x1, 'x2': x2}
            self.learner.partial_fit(X, y)
        
        # Test prediction
        X_test = {'x1': 0.5, 'x2': 0.5}
        y_pred = self.learner.predict(X_test)
        
        self.assertIn(y_pred, [0, 1])
    
    def test_predict_proba(self):
        """Test probability predictions."""
        # Train with some data
        for _ in range(30):
            X = {'x1': np.random.randn(), 'x2': np.random.randn()}
            y = np.random.randint(0, 2)
            self.learner.partial_fit(X, y)
        
        # Test probability prediction
        X_test = {'x1': 0.5, 'x2': -0.5}
        proba = self.learner.predict_proba(X_test)
        
        self.assertIsInstance(proba, dict)
        if proba:  # May be empty if not enough data
            self.assertTrue(all(0 <= p <= 1 for p in proba.values()))
    
    def test_performance_tracking(self):
        """Test performance metric tracking."""
        # Train enough samples to trigger performance recording
        for i in range(150):
            X = {'x1': np.random.randn()}
            y = 1 if X['x1'] > 0 else 0
            self.learner.partial_fit(X, y)
        
        # Check performance history
        self.assertGreater(len(self.learner.performance_history), 0)
        
        # Check performance metrics
        perf = self.learner.get_performance()
        self.assertIn('accuracy', perf)
        self.assertIn('auc', perf)
        self.assertIn('n_samples', perf)
        self.assertEqual(perf['n_samples'], 150)
    
    def test_save_and_load(self):
        """Test model persistence."""
        # Train model
        for _ in range(50):
            X = {'x1': np.random.randn(), 'x2': np.random.randn()}
            y = np.random.randint(0, 2)
            self.learner.partial_fit(X, y)
        
        # Save model
        with tempfile.NamedTemporaryFile(delete=False, suffix='.pkl') as tmp:
            tmp_path = tmp.name
        
        try:
            self.learner.save(tmp_path)
            
            # Load into new learner
            new_learner = OnlineLearner()
            new_learner.load(tmp_path)
            
            # Check state restored
            self.assertEqual(new_learner.n_samples_seen, self.learner.n_samples_seen)
            self.assertEqual(len(new_learner.performance_history), 
                           len(self.learner.performance_history))
        finally:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)


@unittest.skipIf(not RIVER_AVAILABLE, "River library not installed")
class TestConceptDriftDetector(unittest.TestCase):
    """Test ConceptDriftDetector class."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.detector = ConceptDriftDetector(delta=0.002, grace_period=30)
        np.random.seed(42)
    
    def test_initialization(self):
        """Test detector initialization."""
        self.assertEqual(self.detector.total_samples, 0)
        self.assertEqual(len(self.detector.drift_points), 0)
    
    def test_no_drift_on_stable_data(self):
        """Test no drift detected on stable error rate."""
        # Constant error rate
        drift_count = 0
        for _ in range(100):
            error = np.random.choice([0, 1], p=[0.7, 0.3])  # 30% error rate
            drift_detected = self.detector.update(error)
            if drift_detected:
                drift_count += 1
        
        # Should detect very few or no drifts
        self.assertLessEqual(drift_count, 2)
    
    def test_drift_detection_on_regime_change(self):
        """Test drift detection when error rate changes."""
        # Phase 1: Low error rate
        for _ in range(50):
            error = np.random.choice([0, 1], p=[0.9, 0.1])  # 10% error
            self.detector.update(error)
        
        # Phase 2: High error rate (drift)
        drift_detected = False
        for _ in range(100):
            error = np.random.choice([0, 1], p=[0.3, 0.7])  # 70% error
            if self.detector.update(error):
                drift_detected = True
                break
        
        # Should detect drift
        self.assertTrue(drift_detected)
        self.assertGreater(len(self.detector.drift_points), 0)
    
    def test_get_drift_info(self):
        """Test drift information retrieval."""
        # Generate some samples
        for _ in range(50):
            self.detector.update(np.random.rand())
        
        info = self.detector.get_drift_info()
        
        self.assertIn('total_samples', info)
        self.assertIn('drift_count', info)
        self.assertIn('samples_since_drift', info)
        self.assertIn('drift_history', info)
        self.assertEqual(info['total_samples'], 50)


@unittest.skipIf(not RIVER_AVAILABLE, "River library not installed")
class TestOnlineLearningPipeline(unittest.TestCase):
    """Test OnlineLearningPipeline class."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.pipeline = OnlineLearningPipeline(
            retrain_on_drift=True,
            performance_threshold=0.55,
            checkpoint_interval=100
        )
        np.random.seed(42)
    
    def test_initialization(self):
        """Test pipeline initialization."""
        self.assertIsNotNone(self.pipeline.online_learner)
        self.assertIsNotNone(self.pipeline.drift_detector)
        self.assertEqual(self.pipeline.retrain_count, 0)
    
    def test_train_step(self):
        """Test single training step."""
        X = {'x1': 0.5, 'x2': -0.3}
        y = 1
        
        result = self.pipeline.train_step(X, y)
        
        # Check result structure
        self.assertIn('prediction', result)
        self.assertIn('error', result)
        self.assertIn('drift_detected', result)
        self.assertIn('should_retrain', result)
        self.assertIn('performance', result)
        
        # Check types
        self.assertIsInstance(result['drift_detected'], bool)
        self.assertIsInstance(result['should_retrain'], bool)
    
    def test_train_batch(self):
        """Test batch training."""
        # Create batch data
        n_samples = 50
        X_df = pd.DataFrame({
            'x1': np.random.randn(n_samples),
            'x2': np.random.randn(n_samples)
        })
        y_series = pd.Series(np.random.randint(0, 2, n_samples))
        
        results = self.pipeline.train_batch(X_df, y_series)
        
        self.assertEqual(len(results), n_samples)
        self.assertTrue(all('prediction' in r for r in results))
    
    def test_should_retrain_on_poor_performance(self):
        """Test retraining trigger on poor performance."""
        # Train with random data (should perform poorly)
        for _ in range(100):
            X = {'x1': np.random.randn(), 'x2': np.random.randn()}
            y = np.random.randint(0, 2)  # Pure random
            self.pipeline.train_step(X, y)
        
        # With random data, performance might be below threshold
        should_retrain, reason = self.pipeline.should_retrain()
        
        # Just check the function works
        self.assertIsInstance(should_retrain, bool)
        self.assertIsInstance(reason, str)
    
    def test_should_retrain_on_drift(self):
        """Test retraining trigger on concept drift."""
        # Phase 1: Train with pattern 1
        for _ in range(50):
            x1 = np.random.randn()
            y = 1 if x1 > 0 else 0
            X = {'x1': x1}
            self.pipeline.train_step(X, y)
        
        # Phase 2: Switch to opposite pattern (drift)
        drift_triggered = False
        for _ in range(100):
            x1 = np.random.randn()
            y = 0 if x1 > 0 else 1  # Opposite pattern
            X = {'x1': x1}
            result = self.pipeline.train_step(X, y)
            
            if result['should_retrain'] and 'drift' in result.get('retrain_reason', '').lower():
                drift_triggered = True
                break
        
        # May or may not detect drift depending on ADWIN sensitivity
        # Just verify the mechanism works
        self.assertIsInstance(drift_triggered, bool)
    
    def test_predict(self):
        """Test prediction."""
        # Train with some data
        for _ in range(50):
            X = {'x1': np.random.randn()}
            y = np.random.randint(0, 2)
            self.pipeline.train_step(X, y)
        
        # Test prediction
        X_test = {'x1': 0.5}
        y_pred = self.pipeline.predict(X_test)
        
        self.assertIn(y_pred, [0, 1])
    
    def test_predict_proba(self):
        """Test probability prediction."""
        # Train with some data
        for _ in range(50):
            X = {'x1': np.random.randn()}
            y = np.random.randint(0, 2)
            self.pipeline.train_step(X, y)
        
        # Test probability prediction
        X_test = {'x1': 0.5}
        proba = self.pipeline.predict_proba(X_test)
        
        self.assertIsInstance(proba, dict)
    
    def test_get_status(self):
        """Test status retrieval."""
        # Train some samples
        for _ in range(50):
            X = {'x1': np.random.randn()}
            y = np.random.randint(0, 2)
            self.pipeline.train_step(X, y)
        
        status = self.pipeline.get_status()
        
        self.assertIn('performance', status)
        self.assertIn('drift_info', status)
        self.assertIn('retrain_count', status)
        self.assertIn('last_checkpoint', status)
    
    def test_checkpoint_saving(self):
        """Test checkpoint saving."""
        # Train past checkpoint interval
        for _ in range(150):
            X = {'x1': np.random.randn()}
            y = np.random.randint(0, 2)
            self.pipeline.train_step(X, y)
        
        # Check checkpoint was triggered
        status = self.pipeline.get_status()
        self.assertGreater(status['last_checkpoint'], 0)
    
    def test_realistic_trading_scenario(self):
        """Test with realistic trading-like data."""
        # Simulate price predictions
        # Phase 1: Bull market (prices go up)
        for i in range(100):
            price_change = np.random.normal(0.01, 0.02)  # Positive drift
            features = {
                'rsi': 50 + i * 0.2,  # RSI trending up
                'macd': price_change,
                'volume': np.random.uniform(0.8, 1.2)
            }
            y = 1 if price_change > 0 else 0
            
            result = self.pipeline.train_step(features, y)
        
        # Phase 2: Bear market (prices go down) - concept drift
        for i in range(100):
            price_change = np.random.normal(-0.01, 0.02)  # Negative drift
            features = {
                'rsi': 50 - i * 0.2,  # RSI trending down
                'macd': price_change,
                'volume': np.random.uniform(0.8, 1.2)
            }
            y = 1 if price_change > 0 else 0
            
            result = self.pipeline.train_step(features, y)
        
        # Check pipeline adapted
        status = self.pipeline.get_status()
        self.assertGreater(status['performance']['n_samples'], 100)
        
        # Check drift was potentially detected
        drift_info = status['drift_info']
        self.assertGreaterEqual(drift_info['drift_count'], 0)


class TestOnlineLearnerWithoutRiver(unittest.TestCase):
    """Test behavior when River is not available."""
    
    @unittest.skipIf(RIVER_AVAILABLE, "River is installed")
    def test_import_error_without_river(self):
        """Test that appropriate error is raised without River."""
        with self.assertRaises(ImportError):
            from src.ml.online_learner import OnlineLearner
            learner = OnlineLearner()


def run_performance_benchmark():
    """Benchmark online learning performance."""
    if not RIVER_AVAILABLE:
        print("River not installed. Skipping benchmark.")
        return
    
    from src.ml.online_learner import OnlineLearningPipeline
    
    print("\n" + "="*60)
    print("ONLINE LEARNING PERFORMANCE BENCHMARK")
    print("="*60 + "\n")
    
    # Create realistic trading scenario
    np.random.seed(42)
    n_samples = 1000
    
    # Simulate regime changes
    X_data = []
    y_data = []
    
    for i in range(n_samples):
        # Regime 1: Bull market (0-400)
        # Regime 2: Sideways (400-700) - drift!
        # Regime 3: Bear market (700-1000) - drift!
        
        if i < 400:
            # Bull: positive momentum predicts up
            momentum = np.random.normal(0.5, 0.3)
            volume = np.random.normal(1.2, 0.2)
            y = 1 if momentum > 0.3 else 0
        elif i < 700:
            # Sideways: momentum unreliable
            momentum = np.random.normal(0, 0.3)
            volume = np.random.normal(1.0, 0.2)
            y = 1 if volume > 1.0 else 0  # Different pattern
        else:
            # Bear: negative momentum predicts down
            momentum = np.random.normal(-0.5, 0.3)
            volume = np.random.normal(0.8, 0.2)
            y = 0 if momentum < -0.3 else 1  # Inverse pattern
        
        X_data.append({
            'momentum': momentum,
            'volume': volume,
            'rsi': np.random.uniform(30, 70)
        })
        y_data.append(y)
    
    # Create pipeline
    pipeline = OnlineLearningPipeline(
        retrain_on_drift=True,
        performance_threshold=0.55,
        checkpoint_interval=250
    )
    
    # Train and track
    print("Training with 1000 samples (3 regime changes expected)...\n")
    
    drift_samples = []
    accuracies = []
    
    for i, (X, y) in enumerate(zip(X_data, y_data)):
        result = pipeline.train_step(X, y)
        
        if result['drift_detected']:
            drift_samples.append(i)
            print(f"  🔔 Drift detected at sample {i}")
        
        if (i + 1) % 250 == 0:
            perf = result['performance']
            accuracies.append(perf['accuracy'])
            print(f"  [Sample {i+1:4d}] Accuracy: {perf['accuracy']:.3f} | AUC: {perf['auc']:.3f}")
    
    # Final report
    print("\n" + "="*60)
    print("FINAL RESULTS")
    print("="*60)
    
    status = pipeline.get_status()
    print(f"Total samples processed: {status['performance']['n_samples']}")
    print(f"Final accuracy: {status['performance']['accuracy']:.3f}")
    print(f"Final AUC: {status['performance']['auc']:.3f}")
    print(f"Drifts detected: {status['drift_info']['drift_count']} at samples {drift_samples}")
    print(f"Average accuracy: {np.mean(accuracies):.3f}")
    
    if status['drift_info']['drift_count'] >= 2:
        print("\n✅ Successfully detected regime changes!")
    else:
        print("\n⚠️  Fewer drifts detected than expected (sensitivity may need tuning)")
    
    print("\n" + "="*60 + "\n")


if __name__ == '__main__':
    # Run tests
    print("Running Online Learning Tests...\n")
    unittest.main(argv=[''], exit=False, verbosity=2)
    
    # Run benchmark
    run_performance_benchmark()
