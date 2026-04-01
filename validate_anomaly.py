#!/usr/bin/env python
"""Validate anomaly detection implementation."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path.cwd() / "src"))

import numpy as np
import pandas as pd

print("=" * 60)
print("ANOMALY DETECTION VALIDATION")
print("=" * 60)

# Test imports
try:
    from ml.anomaly_detector import (
        IsolationForestDetector,
        StatisticalAnomalyDetector,
        AnomalyRiskManager,
        SKLEARN_AVAILABLE,
        TORCH_AVAILABLE
    )
    print("✅ Import successful")
    print(f"   - sklearn available: {SKLEARN_AVAILABLE}")
    print(f"   - torch available: {TORCH_AVAILABLE}")
except Exception as e:
    print(f"❌ Import failed: {e}")
    sys.exit(1)

if TORCH_AVAILABLE:
    try:
        from ml.anomaly_detector import AutoencoderDetector
        print("✅ AutoencoderDetector imported")
    except Exception as e:
        print(f"⚠️  AutoencoderDetector not available: {e}")

# Test 1: Generate test data
print("\n" + "=" * 60)
print("TEST 1: Data Generation")
print("=" * 60)

np.random.seed(42)
n_samples = 500

# Generate data
prices = 100 * np.exp(np.cumsum(np.random.randn(n_samples) * 0.01))
volumes = np.random.uniform(1e6, 2e6, n_samples)
returns = np.diff(prices) / prices[:-1]
returns = np.concatenate([[0], returns])
volatility = pd.Series(returns).rolling(20).std().fillna(0).values

features = pd.DataFrame({
    'returns': returns,
    'volume': volumes,
    'volatility': volatility,
    'rsi': np.random.uniform(30, 70, n_samples),
    'vwap_dev': np.random.uniform(-0.01, 0.01, n_samples)
})

print(f"✅ Generated {n_samples} samples")
print(f"   - Features shape: {features.shape}")
print(f"   - Feature columns: {list(features.columns)}")

# Test 2: IsolationForest Detector
if SKLEARN_AVAILABLE:
    print("\n" + "=" * 60)
    print("TEST 2: IsolationForest Detector")
    print("=" * 60)
    
    try:
        detector = IsolationForestDetector(contamination=0.05)
        print("✅ IsolationForestDetector initialized")
        
        # Fit on first 400 samples
        train_features = features.iloc[:400]
        detector.fit(train_features)
        print(f"✅ Detector fitted on {len(train_features)} samples")
        
        # Predict on test data
        test_features = features.iloc[400:]
        predictions = detector.predict(test_features)
        anomalies = np.sum(predictions == -1)
        print(f"✅ Predictions made: {anomalies} anomalies detected out of {len(test_features)}")
        
        # Scores
        scores = detector.score_samples(test_features)
        print(f"✅ Anomaly scores computed: min={scores.min():.4f}, max={scores.max():.4f}")
    except Exception as e:
        print(f"❌ IsolationForest test failed: {e}")
        import traceback
        traceback.print_exc()

# Test 3: Statistical Detector
print("\n" + "=" * 60)
print("TEST 3: Statistical Anomaly Detector")
print("=" * 60)

try:
    detector = StatisticalAnomalyDetector(window=100, z_threshold=3.0)
    print("✅ StatisticalAnomalyDetector initialized")
    
    # Test price anomaly
    price_anom, z_scores = detector.detect_price_anomaly(prices)
    anomalies_count = np.sum(price_anom)
    print(f"✅ Price anomalies: {anomalies_count} detected")
    
    # Test volume anomaly
    vol_anom, vol_ratios = detector.detect_volume_anomaly(volumes)
    vol_anomalies = np.sum(vol_anom)
    print(f"✅ Volume anomalies: {vol_anomalies} detected")
    
    # Test volatility spike
    vol_spike = detector.detect_volatility_spike(returns)
    vol_spikes = np.sum(vol_spike)
    print(f"✅ Volatility spikes: {vol_spikes} detected")
except Exception as e:
    print(f"❌ Statistical detector test failed: {e}")
    import traceback
    traceback.print_exc()

# Test 4: Autoencoder (if available)
if TORCH_AVAILABLE:
    print("\n" + "=" * 60)
    print("TEST 4: Autoencoder Detector")
    print("=" * 60)
    
    try:
        ae_detector = AutoencoderDetector(input_dim=features.shape[1], hidden_dim=16)
        print("✅ AutoencoderDetector initialized")
        
        # Fit on training data
        train_features = features.iloc[:400]
        ae_detector.fit(train_features, epochs=10, verbose=False)
        print(f"✅ Autoencoder fitted")
        print(f"   - Reconstruction threshold: {ae_detector.reconstruction_threshold:.6f}")
        
        # Predict
        test_features = features.iloc[400:]
        predictions = ae_detector.predict(test_features)
        anomalies = np.sum(predictions == -1)
        print(f"✅ Predictions made: {anomalies} anomalies detected")
        
        # Scores
        scores = ae_detector.score_samples(test_features)
        print(f"✅ Anomaly scores computed: min={scores.min():.4f}, max={scores.max():.4f}")
    except Exception as e:
        print(f"❌ Autoencoder test failed: {e}")
        import traceback
        traceback.print_exc()

# Test 5: Risk Manager
if SKLEARN_AVAILABLE:
    print("\n" + "=" * 60)
    print("TEST 5: AnomalyRiskManager (Ensemble)")
    print("=" * 60)
    
    try:
        mgr = AnomalyRiskManager(risk_reduction_factor=0.5, ensemble_method='voting')
        print("✅ AnomalyRiskManager initialized")
        
        # Fit
        train_features = features.iloc[:400]
        mgr.fit(train_features, autoencoder_epochs=5)
        print("✅ Risk manager fitted with all detectors")
        
        # Test detection
        test_features = features.iloc[400:]
        test_prices = prices[400:]
        test_volumes = volumes[400:]
        
        anomaly_count = 0
        for i in range(min(10, len(test_features))):
            result = mgr.detect_anomalies(
                test_features.iloc[i:i+1],
                test_prices[:i+1] if i > 0 else test_prices[0:1],
                test_volumes[:i+1] if i > 0 else test_volumes[0:1]
            )
            
            if result['is_anomaly']:
                anomaly_count += 1
        
        print(f"✅ Detection completed: {anomaly_count} anomalies in 10 samples")
        
        # Position sizing
        adjusted = mgr.adjust_position_size(10000.0, {
            'is_anomaly': True,
            'anomaly_types': ['test'],
            'risk_multiplier': 0.5
        })
        print(f"✅ Position sizing: $10,000 -> ${adjusted:.2f}")
        
        # Report
        report = mgr.get_anomaly_report()
        print(f"✅ Report generated: {report['total_anomalies']} total anomalies")
    except Exception as e:
        print(f"❌ Risk manager test failed: {e}")
        import traceback
        traceback.print_exc()

print("\n" + "=" * 60)
print("✅ VALIDATION COMPLETE")
print("=" * 60)
