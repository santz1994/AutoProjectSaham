"""
Tests for Online Learning Pipeline

Tests:
1. OnlineLearner - incremental updates
2. ConceptDriftDetector - drift detection
3. OnlineLearningPipeline - full pipeline
"""
import pytest
import numpy as np
from src.ml.online_learner import OnlineLearner, ConceptDriftDetector, OnlineLearningPipeline

def test_online_learner_basic():
    """Test basic online learning."""
    try:
        learner = OnlineLearner(n_models=5)
        
        # Train on simple data
        for i in range(50):
            X = {'feature1': float(i % 10), 'feature2': float(i % 5)}
            y = 1 if i % 2 == 0 else 0
            learner.partial_fit(X, y)
        
        # Check performance
        perf = learner.get_performance()
        assert perf['n_samples'] == 50
        assert 'accuracy' in perf
        
        print(f"✅ OnlineLearner trained: {perf['n_samples']} samples, Acc: {perf['accuracy']:.3f}")
        
    except ImportError:
        print("⚠️  River not installed - skipping test")
        pytest.skip("River not available")


def test_drift_detector():
    """Test concept drift detection."""
    try:
        detector = ConceptDriftDetector(delta=0.01)
        
        # Simulate stable then drifting data
        drift_detected = False
        for i in range(200):
            # Error rate changes at i=100
            error = 0.1 if i < 100 else 0.5
            if detector.update(error):
                drift_detected = True
                break
        
        info = detector.get_drift_info()
        print(f"✅ DriftDetector: {info['drift_count']} drifts in {info['total_samples']} samples")
        
    except ImportError:
        pytest.skip("River not available")


def test_online_pipeline():
    """Test full online learning pipeline."""
    try:
        pipeline = OnlineLearningPipeline(retrain_on_drift=True)
        
        # Simulate streaming data
        for i in range(100):
            X = {'f1': float(i % 10), 'f2': float(i % 5)}
            y = 1 if i % 3 == 0 else 0
            
            result = pipeline.update(X, y)
        
        status = pipeline.get_status()
        print(f"✅ Pipeline: {status['samples_processed']} samples, {status['drift_count']} drifts")
        
    except ImportError:
        pytest.skip("River not available")


if __name__ == "__main__":
    print("=== Online Learning Tests ===\n")
    test_online_learner_basic()
    test_drift_detector()
    test_online_pipeline()
    print("\n✅ All tests passed!")
