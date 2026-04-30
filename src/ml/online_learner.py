"""
Online Learning Pipeline

Incremental model updates without full retraining using River library.
Enables continuous adaptation to market changes with:
1. Streaming feature computation
2. Incremental model updates (partial_fit)
3. Concept drift detection (ADWIN, DDM)
4. Adaptive retraining triggers
5. Performance monitoring

This allows the model to adapt to market regime changes
without expensive full retraining cycles.
"""
from __future__ import annotations

from typing import Dict, List, Optional, Tuple
from datetime import datetime
import numpy as np
import pandas as pd
import json
import os

# River for online learning
try:
    from river import ensemble, tree, metrics, drift
    RIVER_AVAILABLE = True
except ImportError:
    RIVER_AVAILABLE = False
    ensemble = None
    tree = None
    metrics = None
    drift = None


class OnlineLearner:
    """
    Online machine learning model that updates incrementally.
    
    Uses River's Adaptive Random Forest for streaming classification.
    Suitable for time-series data where distribution changes over time.
    """
    
    def __init__(
        self,
        n_models: int = 10,
        max_features: Optional[int] = None,
        grace_period: int = 50,
        split_confidence: float = 0.01
    ):
        """
        Initialize online learner.
        
        Args:
            n_models: Number of trees in adaptive random forest
            max_features: Max features per tree (None = sqrt(n_features))
            grace_period: Number of instances before split attempt
            split_confidence: Confidence level for Hoeffding bound
        """
        if not RIVER_AVAILABLE:
            raise ImportError(
                "River not installed. Install with: pip install river"
            )
        
        self.model = ensemble.AdaptiveRandomForestClassifier(
            n_models=n_models,
            max_features=max_features,
            grace_period=grace_period,
            split_confidence=split_confidence
        )
        
        # Metrics
        self.accuracy_metric = metrics.Accuracy()
        self.auc_metric = metrics.ROCAUC()
        
        # Performance history
        self.performance_history = []
        
        # Training counter
        self.n_samples_seen = 0
    
    def partial_fit(self, X: Dict[str, float], y: int) -> None:
        """
        Update model with a single sample.
        
        Args:
            X: Feature dictionary {feature_name: value}
            y: True label (0 or 1)
        """
        # Make prediction before learning (for metrics)
        try:
            y_pred = self.model.predict_proba_one(X)
            
            # Update metrics
            if y_pred:
                self.accuracy_metric.update(y, max(y_pred, key=y_pred.get))
                if len(y_pred) == 2:  # Binary classification
                    self.auc_metric.update(y, y_pred.get(1, 0.5))
        except Exception:
            pass
        
        # Learn from sample
        self.model.learn_one(X, y)
        self.n_samples_seen += 1
        
        # Record performance periodically
        if self.n_samples_seen % 100 == 0:
            self.performance_history.append({
                'n_samples': self.n_samples_seen,
                'accuracy': self.accuracy_metric.get(),
                'auc': self.auc_metric.get(),
                'timestamp': datetime.now().isoformat()
            })
    
    def predict_proba(self, X: Dict[str, float]) -> Dict[int, float]:
        """
        Predict class probabilities for a sample.
        
        Args:
            X: Feature dictionary
            
        Returns:
            Dictionary {class: probability}
        """
        return self.model.predict_proba_one(X)
    
    def predict(self, X: Dict[str, float]) -> int:
        """
        Predict class for a sample.
        
        Args:
            X: Feature dictionary
            
        Returns:
            Predicted class (0 or 1)
        """
        try:
            return self.model.predict_one(X)
        except Exception:
            return 0  # Default to class 0 if not enough data
    
    def get_performance(self) -> Dict[str, float]:
        """
        Get current performance metrics.
        
        Returns:
            Dictionary with accuracy and AUC
        """
        return {
            'accuracy': self.accuracy_metric.get(),
            'auc': self.auc_metric.get(),
            'n_samples': self.n_samples_seen
        }
    
    def save(self, filepath: str) -> None:
        """
        Save model and metrics to file.
        
        Args:
            filepath: Path to save file
        """
        import pickle
        
        state = {
            'model': self.model,
            'performance_history': self.performance_history,
            'n_samples_seen': self.n_samples_seen
        }
        
        os.makedirs(os.path.dirname(filepath) or '.', exist_ok=True)
        
        with open(filepath, 'wb') as f:
            pickle.dump(state, f)
    
    def load(self, filepath: str) -> None:
        """
        Load model and metrics from file.
        
        Args:
            filepath: Path to load file
        """
        import pickle
        
        with open(filepath, 'rb') as f:
            state = pickle.load(f)
        
        self.model = state['model']
        self.performance_history = state['performance_history']
        self.n_samples_seen = state['n_samples_seen']


class ConceptDriftDetector:
    """
    Detect concept drift in streaming data.
    
    Uses ADWIN (Adaptive Windowing) to detect changes in data distribution.
    Triggers retraining when significant drift detected.
    """
    
    def __init__(
        self,
        delta: float = 0.002,
        grace_period: int = 10,
        min_window_size: int = 5
    ):
        """
        Initialize drift detector.
        
        Args:
            delta: Confidence level (lower = more sensitive)
            grace_period: Minimum samples before detection
            min_window_size: Minimum window size for ADWIN
        """
        if not RIVER_AVAILABLE:
            raise ImportError("River not installed")
        
        self.adwin = drift.ADWIN(delta=delta)
        self.grace_period = grace_period
        self.min_window_size = min_window_size
        
        # Drift history
        self.drift_points = []
        self.samples_since_drift = 0
        self.total_samples = 0
    
    def update(self, error: float) -> bool:
        """
        Update drift detector with new prediction error.
        
        Args:
            error: Prediction error (0 = correct, 1 = incorrect)
            
        Returns:
            True if drift detected, False otherwise
        """
        self.total_samples += 1
        self.samples_since_drift += 1
        
        # Wait for grace period
        if self.total_samples < self.grace_period:
            return False
        
        # Update ADWIN
        drift_detected = self.adwin.update(error)
        
        if drift_detected:
            self.drift_points.append({
                'sample': self.total_samples,
                'samples_since_last': self.samples_since_drift,
                'timestamp': datetime.now().isoformat()
            })
            self.samples_since_drift = 0
            return True
        
        return False
    
    def get_drift_info(self) -> Dict:
        """
        Get drift detection statistics.
        
        Returns:
            Dictionary with drift information
        """
        return {
            'total_samples': self.total_samples,
            'drift_count': len(self.drift_points),
            'samples_since_drift': self.samples_since_drift,
            'drift_history': self.drift_points[-5:]  # Last 5 drifts
        }


class OnlineLearningPipeline:
    """
    Complete online learning pipeline with drift detection and retraining.
    
    Manages:
    1. Incremental model updates
    2. Concept drift monitoring
    3. Automatic retraining triggers
    4. Performance tracking
    """
    
    def __init__(
        self,
        retrain_on_drift: bool = True,
        performance_threshold: float = 0.55,
        drift_delta: float = 0.002,
        checkpoint_interval: int = 1000
    ):
        """
        Initialize online learning pipeline.
        
        Args:
            retrain_on_drift: Trigger retraining when drift detected
            performance_threshold: Min accuracy to avoid retraining
            drift_delta: Drift detection sensitivity
            checkpoint_interval: Save checkpoint every N samples
        """
        self.online_learner = OnlineLearner()
        self.drift_detector = ConceptDriftDetector(delta=drift_delta)
        
        self.retrain_on_drift = retrain_on_drift
        self.performance_threshold = performance_threshold
        self.checkpoint_interval = checkpoint_interval
        
        # Retraining triggers
        self.retrain_count = 0
        self.last_checkpoint_sample = 0
    
    def should_retrain(self) -> Tuple[bool, str]:
        """
        Check if model should be retrained.
        
        Returns:
            Tuple of (should_retrain, reason)
        """
        performance = self.online_learner.get_performance()
        
        # Check performance degradation
        if performance['accuracy'] < self.performance_threshold:
            return True, f"Performance below threshold ({performance['accuracy']:.3f} < {self.performance_threshold})"
        
        # Check drift detection
        drift_info = self.drift_detector.get_drift_info()
        if self.retrain_on_drift and drift_info['samples_since_drift'] == 0:
            return True, "Concept drift detected"
        
        return False, "No retraining needed"
    
    def train_step(
        self,
        X: Dict[str, float],
        y: int
    ) -> Dict[str, any]:
        """
        Single training step with drift detection.
        
        Args:
            X: Feature dictionary
            y: True label
            
        Returns:
            Dictionary with step results
        """
        # Make prediction
        y_pred_proba = self.online_learner.predict_proba(X)
        y_pred = max(y_pred_proba, key=y_pred_proba.get) if y_pred_proba else 0
        
        # Calculate error for drift detection
        error = 1.0 if y_pred != y else 0.0
        
        # Update drift detector
        drift_detected = self.drift_detector.update(error)
        
        # Update online learner
        self.online_learner.partial_fit(X, y)
        
        # Check retraining
        should_retrain, retrain_reason = self.should_retrain()
        
        # Checkpoint
        n_samples = self.online_learner.n_samples_seen
        if n_samples - self.last_checkpoint_sample >= self.checkpoint_interval:
            self.save_checkpoint(f"models/online_checkpoint_{n_samples}.pkl")
            self.last_checkpoint_sample = n_samples
        
        return {
            'prediction': y_pred,
            'error': error,
            'drift_detected': drift_detected,
            'should_retrain': should_retrain,
            'retrain_reason': retrain_reason if should_retrain else None,
            'performance': self.online_learner.get_performance()
        }
    
    def train_batch(
        self,
        X_df: pd.DataFrame,
        y_series: pd.Series
    ) -> List[Dict]:
        """
        Train on a batch of data sequentially.
        
        Args:
            X_df: Feature DataFrame
            y_series: Label Series
            
        Returns:
            List of step results
        """
        results = []
        
        for idx in range(len(X_df)):
            X_dict = X_df.iloc[idx].to_dict()
            y = int(y_series.iloc[idx])
            
            result = self.train_step(X_dict, y)
            results.append(result)
        
        return results
    
    def predict(self, X: Dict[str, float]) -> int:
        """Predict class for a sample."""
        return self.online_learner.predict(X)
    
    def predict_proba(self, X: Dict[str, float]) -> Dict[int, float]:
        """Predict probabilities for a sample."""
        return self.online_learner.predict_proba(X)
    
    def get_status(self) -> Dict:
        """
        Get pipeline status.
        
        Returns:
            Dictionary with pipeline statistics
        """
        return {
            'performance': self.online_learner.get_performance(),
            'drift_info': self.drift_detector.get_drift_info(),
            'retrain_count': self.retrain_count,
            'last_checkpoint': self.last_checkpoint_sample
        }
    
    def save_checkpoint(self, filepath: str) -> None:
        """Save pipeline checkpoint."""
        self.online_learner.save(filepath)
        print(f"Checkpoint saved: {filepath}")
    
    def load_checkpoint(self, filepath: str) -> None:
        """Load pipeline checkpoint."""
        self.online_learner.load(filepath)
        print(f"Checkpoint loaded: {filepath}")


if __name__ == "__main__":
    # Example usage
    print("=== Online Learning Pipeline Example ===\n")
    
    if not RIVER_AVAILABLE:
        print("ERROR: River library not installed")
        print("Install with: pip install river")
        exit(1)
    
    # Generate synthetic streaming data
    np.random.seed(42)
    n_samples = 1000
    
    # Create features
    X_data = []
    y_data = []
    
    for i in range(n_samples):
        # Simulate regime change at sample 500
        if i < 500:
            # Regime 1: positive correlation
            x1 = np.random.normal(0, 1)
            x2 = x1 + np.random.normal(0, 0.5)
            y = 1 if x1 + x2 > 0 else 0
        else:
            # Regime 2: negative correlation (concept drift)
            x1 = np.random.normal(0, 1)
            x2 = -x1 + np.random.normal(0, 0.5)
            y = 1 if x1 - x2 > 0 else 0
        
        X_data.append({'x1': x1, 'x2': x2, 'x3': np.random.normal(0, 1)})
        y_data.append(y)
    
    # Create pipeline
    pipeline = OnlineLearningPipeline(
        retrain_on_drift=True,
        performance_threshold=0.55,
        drift_delta=0.002,
        checkpoint_interval=250
    )
    
    # Stream training
    print("Training with streaming data...")
    drift_detected_at = []
    
    for i, (X, y) in enumerate(zip(X_data, y_data)):
        result = pipeline.train_step(X, y)
        
        if result['drift_detected']:
            drift_detected_at.append(i)
            print(f"  [Sample {i}] Drift detected!")
        
        # Print progress
        if (i + 1) % 250 == 0:
            perf = result['performance']
            print(f"  [Sample {i+1}] Accuracy: {perf['accuracy']:.3f}, AUC: {perf['auc']:.3f}")
    
    # Final status
    print("\n=== Final Status ===")
    status = pipeline.get_status()
    print(f"Total samples: {status['performance']['n_samples']}")
    print(f"Final accuracy: {status['performance']['accuracy']:.3f}")
    print(f"Final AUC: {status['performance']['auc']:.3f}")
    print(f"Drifts detected: {status['drift_info']['drift_count']} at samples {drift_detected_at}")
    print(f"Checkpoints saved: {status['last_checkpoint']}")
