"""
Online Learning Integration

Integrates online learning pipeline with the main AutoSaham system.
Provides:
1. Conversion between batch models and online models
2. Hybrid training (batch + online updates)
3. Model switching based on performance
4. Integration with existing feature store and labeler
"""
from __future__ import annotations

from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime
from pathlib import Path
import numpy as np
import pandas as pd
import joblib
import logging

try:
    from .online_learner import OnlineLearningPipeline, RIVER_AVAILABLE
    from .online_dashboard import OnlineLearningDashboard
except ImportError:
    RIVER_AVAILABLE = False
    OnlineLearningPipeline = None
    OnlineLearningDashboard = None

logger = logging.getLogger(__name__)


class HybridLearningSystem:
    """
    Hybrid system combining batch and online learning.
    
    Strategy:
    1. Start with batch-trained model (LightGBM, XGBoost, etc.)
    2. Use online learner for incremental updates
    3. Switch to online model when it outperforms batch model
    4. Periodically retrain batch model with accumulated data
    """
    
    def __init__(
        self,
        batch_model: Any = None,
        model_dir: str = "models",
        performance_threshold: float = 0.55,
        switch_threshold: float = 0.02,  # Switch when online model is 2% better
        retrain_interval: int = 10000  # Retrain batch model every 10k samples
    ):
        """
        Initialize hybrid learning system.
        
        Args:
            batch_model: Pre-trained batch model (sklearn-compatible)
            model_dir: Directory for model storage
            performance_threshold: Minimum acceptable accuracy
            switch_threshold: Performance difference to switch models
            retrain_interval: Samples before batch model retraining
        """
        if not RIVER_AVAILABLE:
            raise ImportError(
                "River library required for online learning. "
                "Install with: pip install river"
            )
        
        self.batch_model = batch_model
        self.model_dir = Path(model_dir)
        self.model_dir.mkdir(parents=True, exist_ok=True)
        
        # Initialize online pipeline
        self.online_pipeline = OnlineLearningPipeline(
            retrain_on_drift=True,
            performance_threshold=performance_threshold,
            checkpoint_interval=1000
        )
        
        # Initialize dashboard
        self.dashboard = OnlineLearningDashboard(
            log_dir=str(self.model_dir / "online_learning_logs")
        )
        
        # Configuration
        self.performance_threshold = performance_threshold
        self.switch_threshold = switch_threshold
        self.retrain_interval = retrain_interval
        
        # State
        self.active_model = 'batch' if batch_model is not None else 'online'
        self.samples_since_batch_retrain = 0
        self.accumulated_data = []
        
        # Performance tracking
        self.batch_model_accuracy = []
        self.online_model_accuracy = []
        
        logger.info(f"Hybrid learning system initialized. Active model: {self.active_model}")
    
    def predict(self, X: Dict[str, float]) -> Tuple[int, float]:
        """
        Make prediction using active model.
        
        Args:
            X: Feature dictionary
            
        Returns:
            Tuple of (prediction, confidence)
        """
        if self.active_model == 'batch' and self.batch_model is not None:
            # Use batch model
            X_array = self._dict_to_array(X)
            
            if hasattr(self.batch_model, 'predict_proba'):
                proba = self.batch_model.predict_proba(X_array)[0]
                pred = np.argmax(proba)
                conf = np.max(proba)
            else:
                pred = self.batch_model.predict(X_array)[0]
                conf = 0.5
            
            return int(pred), float(conf)
        else:
            # Use online model
            proba_dict = self.online_pipeline.predict_proba(X)
            
            if proba_dict:
                pred = max(proba_dict, key=proba_dict.get)
                conf = proba_dict[pred]
            else:
                pred = 0
                conf = 0.5
            
            return int(pred), float(conf)
    
    def update(
        self,
        X: Dict[str, float],
        y: int,
        feature_names: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Update model with new sample (online learning).
        
        Args:
            X: Feature dictionary
            y: True label
            feature_names: Ordered feature names for batch model
            
        Returns:
            Dictionary with update results
        """
        self.samples_since_batch_retrain += 1
        
        # Make prediction with both models (if batch exists)
        batch_pred = None
        online_pred = None
        
        if self.batch_model is not None:
            batch_pred, _ = self._predict_batch(X, feature_names)
        
        # Update online model
        result = self.online_pipeline.train_step(X, y)
        online_pred = result['prediction']
        
        # Track performance
        if self.batch_model is not None and batch_pred is not None:
            self.batch_model_accuracy.append(1.0 if batch_pred == y else 0.0)
            if len(self.batch_model_accuracy) > 1000:
                self.batch_model_accuracy.pop(0)
        
        self.online_model_accuracy.append(1.0 if online_pred == y else 0.0)
        if len(self.online_model_accuracy) > 1000:
            self.online_model_accuracy.pop(0)
        
        # Decide if model switch is needed
        should_switch, switch_reason = self._should_switch_model()
        if should_switch:
            self.active_model = switch_reason.split('to ')[1]
            logger.info(f"Model switched: {switch_reason}")
        
        # Accumulate data for batch retraining
        X_array = self._dict_to_array(X, feature_names)
        self.accumulated_data.append((X_array, y))
        
        # Keep only recent data
        if len(self.accumulated_data) > self.retrain_interval:
            self.accumulated_data = self.accumulated_data[-self.retrain_interval:]
        
        # Check if batch model retraining is needed
        should_retrain_batch = (
            self.samples_since_batch_retrain >= self.retrain_interval
            and len(self.accumulated_data) >= 1000
        )
        
        # Log to dashboard
        self.dashboard.log_prediction(
            features=X,
            prediction=online_pred,
            true_label=y,
            confidence=result.get('performance', {}).get('accuracy', 0.5),
            drift_detected=result['drift_detected'],
            should_retrain=result['should_retrain'] or should_retrain_batch,
            performance=result['performance']
        )
        
        return {
            'batch_prediction': batch_pred,
            'online_prediction': online_pred,
            'active_model': self.active_model,
            'drift_detected': result['drift_detected'],
            'should_retrain_online': result['should_retrain'],
            'should_retrain_batch': should_retrain_batch,
            'model_switched': should_switch,
            'performance': result['performance']
        }
    
    def batch_update(
        self,
        X_df: pd.DataFrame,
        y_series: pd.Series
    ) -> List[Dict]:
        """
        Update with batch of samples.
        
        Args:
            X_df: Feature DataFrame
            y_series: Label Series
            
        Returns:
            List of update results
        """
        results = []
        feature_names = list(X_df.columns)
        
        for idx in range(len(X_df)):
            X_dict = X_df.iloc[idx].to_dict()
            y = int(y_series.iloc[idx])
            
            result = self.update(X_dict, y, feature_names)
            results.append(result)
        
        return results
    
    def retrain_batch_model(
        self,
        model_class: Optional[Any] = None,
        **model_kwargs
    ) -> bool:
        """
        Retrain batch model with accumulated data.
        
        Args:
            model_class: Model class to use (e.g., LGBMClassifier)
            **model_kwargs: Model initialization parameters
            
        Returns:
            True if retraining successful
        """
        if len(self.accumulated_data) < 100:
            logger.warning("Insufficient data for batch retraining")
            return False
        
        try:
            # Prepare data
            X_list, y_list = zip(*self.accumulated_data)
            X_array = np.vstack(X_list)
            y_array = np.array(y_list)
            
            # Train new model
            if model_class is not None:
                new_model = model_class(**model_kwargs)
                new_model.fit(X_array, y_array)
                self.batch_model = new_model
                
                logger.info(f"Batch model retrained with {len(y_array)} samples")
            elif self.batch_model is not None:
                # Retrain existing model if it supports partial_fit
                if hasattr(self.batch_model, 'fit'):
                    self.batch_model.fit(X_array, y_array)
                    logger.info(f"Batch model retrained with {len(y_array)} samples")
            
            self.samples_since_batch_retrain = 0
            
            # Save model
            self.save_batch_model()
            
            return True
            
        except Exception as e:
            logger.error(f"Batch model retraining failed: {e}")
            return False
    
    def _should_switch_model(self) -> Tuple[bool, str]:
        """
        Determine if model switch is beneficial.
        
        Returns:
            Tuple of (should_switch, reason)
        """
        if self.batch_model is None:
            return False, "No batch model available"
        
        if len(self.batch_model_accuracy) < 100 or len(self.online_model_accuracy) < 100:
            return False, "Insufficient data for comparison"
        
        batch_acc = np.mean(self.batch_model_accuracy[-100:])
        online_acc = np.mean(self.online_model_accuracy[-100:])
        
        if self.active_model == 'batch':
            # Switch to online if it's significantly better
            if online_acc > batch_acc + self.switch_threshold:
                return True, f"Switching to online (online: {online_acc:.3f} > batch: {batch_acc:.3f})"
        else:
            # Switch to batch if it's significantly better
            if batch_acc > online_acc + self.switch_threshold:
                return True, f"Switching to batch (batch: {batch_acc:.3f} > online: {online_acc:.3f})"
        
        return False, "No switch needed"
    
    def _predict_batch(
        self,
        X: Dict[str, float],
        feature_names: Optional[List[str]] = None
    ) -> Tuple[Optional[int], Optional[float]]:
        """
        Make prediction with batch model.
        
        Args:
            X: Feature dictionary
            feature_names: Ordered feature names
            
        Returns:
            Tuple of (prediction, confidence)
        """
        if self.batch_model is None:
            return None, None
        
        try:
            X_array = self._dict_to_array(X, feature_names)
            
            if hasattr(self.batch_model, 'predict_proba'):
                proba = self.batch_model.predict_proba(X_array)[0]
                pred = np.argmax(proba)
                conf = np.max(proba)
            else:
                pred = self.batch_model.predict(X_array)[0]
                conf = 0.5
            
            return int(pred), float(conf)
        except Exception as e:
            logger.error(f"Batch prediction failed: {e}")
            return None, None
    
    def _dict_to_array(
        self,
        X: Dict[str, float],
        feature_names: Optional[List[str]] = None
    ) -> np.ndarray:
        """
        Convert feature dictionary to array for batch model.
        
        Args:
            X: Feature dictionary
            feature_names: Ordered feature names
            
        Returns:
            Feature array (1, n_features)
        """
        if feature_names is None:
            feature_names = sorted(X.keys())
        
        values = [X.get(fname, 0.0) for fname in feature_names]
        return np.array(values).reshape(1, -1)
    
    def get_status(self) -> Dict:
        """
        Get system status.
        
        Returns:
            Dictionary with system status
        """
        status = {
            'active_model': self.active_model,
            'samples_since_batch_retrain': self.samples_since_batch_retrain,
            'accumulated_samples': len(self.accumulated_data),
            'online_pipeline': self.online_pipeline.get_status(),
            'dashboard_metrics': self.dashboard.get_current_metrics()
        }
        
        if len(self.batch_model_accuracy) > 0:
            status['batch_model_accuracy'] = float(np.mean(self.batch_model_accuracy[-100:]))
        
        if len(self.online_model_accuracy) > 0:
            status['online_model_accuracy'] = float(np.mean(self.online_model_accuracy[-100:]))
        
        return status
    
    def print_status(self) -> None:
        """Print system status to console."""
        self.dashboard.print_dashboard()
        
        print("\n" + "="*80)
        print("HYBRID LEARNING SYSTEM STATUS".center(80))
        print("="*80 + "\n")
        
        status = self.get_status()
        
        print(f"Active Model:                 {status['active_model'].upper()}")
        print(f"Samples Since Batch Retrain:  {status['samples_since_batch_retrain']:,}")
        print(f"Accumulated Training Samples: {status['accumulated_samples']:,}")
        
        if 'batch_model_accuracy' in status:
            print(f"Batch Model Accuracy (100):   {status['batch_model_accuracy']:.3f}")
        if 'online_model_accuracy' in status:
            print(f"Online Model Accuracy (100):  {status['online_model_accuracy']:.3f}")
        
        print("\n" + "="*80 + "\n")
    
    def save_batch_model(self, filename: Optional[str] = None) -> str:
        """
        Save batch model to file.
        
        Args:
            filename: Custom filename (optional)
            
        Returns:
            Path to saved file
        """
        if self.batch_model is None:
            logger.warning("No batch model to save")
            return ""
        
        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"batch_model_{timestamp}.pkl"
        
        filepath = self.model_dir / filename
        
        joblib.dump(self.batch_model, filepath)
        logger.info(f"Batch model saved to {filepath}")
        
        return str(filepath)
    
    def load_batch_model(self, filepath: str) -> None:
        """
        Load batch model from file.
        
        Args:
            filepath: Path to model file
        """
        self.batch_model = joblib.load(filepath)
        self.active_model = 'batch'
        logger.info(f"Batch model loaded from {filepath}")
    
    def save_checkpoint(self, checkpoint_dir: Optional[str] = None) -> Dict[str, str]:
        """
        Save complete system checkpoint.
        
        Args:
            checkpoint_dir: Directory for checkpoint (optional)
            
        Returns:
            Dictionary with paths to saved files
        """
        if checkpoint_dir is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            checkpoint_dir = self.model_dir / f"checkpoint_{timestamp}"
        
        checkpoint_path = Path(checkpoint_dir)
        checkpoint_path.mkdir(parents=True, exist_ok=True)
        
        paths = {}
        
        # Save batch model
        if self.batch_model is not None:
            batch_path = checkpoint_path / "batch_model.pkl"
            joblib.dump(self.batch_model, batch_path)
            paths['batch_model'] = str(batch_path)
        
        # Save online pipeline
        online_path = checkpoint_path / "online_pipeline.pkl"
        self.online_pipeline.save_checkpoint(str(online_path))
        paths['online_pipeline'] = str(online_path)
        
        # Save dashboard
        dashboard_path = checkpoint_path / "dashboard.json"
        self.dashboard.save_dashboard(str(dashboard_path))
        paths['dashboard'] = str(dashboard_path)
        
        # Save system state
        state = {
            'active_model': self.active_model,
            'samples_since_batch_retrain': self.samples_since_batch_retrain,
            'performance_threshold': self.performance_threshold,
            'switch_threshold': self.switch_threshold,
            'retrain_interval': self.retrain_interval
        }
        state_path = checkpoint_path / "system_state.json"
        import json
        with open(state_path, 'w') as f:
            json.dump(state, f, indent=2)
        paths['system_state'] = str(state_path)
        
        logger.info(f"Checkpoint saved to {checkpoint_path}")
        
        return paths


if __name__ == "__main__":
    # Demo hybrid learning system
    print("=== Hybrid Learning System Demo ===\n")
    
    if not RIVER_AVAILABLE:
        print("ERROR: River library not installed")
        print("Install with: pip install river")
        exit(1)
    
    # Create simple batch model (sklearn)
    try:
        from sklearn.ensemble import RandomForestClassifier
        
        # Train initial batch model
        print("Training initial batch model...")
        np.random.seed(42)
        X_init = np.random.randn(500, 3)
        y_init = (X_init[:, 0] + X_init[:, 1] > 0).astype(int)
        
        batch_model = RandomForestClassifier(n_estimators=10, random_state=42)
        batch_model.fit(X_init, y_init)
        
        # Create hybrid system
        system = HybridLearningSystem(
            batch_model=batch_model,
            performance_threshold=0.55,
            switch_threshold=0.02
        )
        
        # Simulate streaming data with concept drift
        print("\nSimulating 500 predictions with concept drift...\n")
        
        for i in range(500):
            # Concept drift at sample 250
            if i < 250:
                x1, x2, x3 = np.random.randn(3)
                y = 1 if x1 + x2 > 0 else 0
            else:
                x1, x2, x3 = np.random.randn(3)
                y = 1 if x1 - x2 > 0 else 0  # Pattern changed
            
            X_dict = {'x1': x1, 'x2': x2, 'x3': x3}
            
            result = system.update(X_dict, y, feature_names=['x1', 'x2', 'x3'])
            
            if (i + 1) % 100 == 0:
                print(f"[Sample {i+1}] Active: {result['active_model']}, "
                      f"Accuracy: {result['performance']['accuracy']:.3f}")
        
        # Print final status
        print("\n")
        system.print_status()
        
        # Save checkpoint
        paths = system.save_checkpoint()
        print(f"\n✅ Checkpoint saved:")
        for key, path in paths.items():
            print(f"   {key}: {path}")
        
    except ImportError:
        print("ERROR: scikit-learn not installed")
        print("Install with: pip install scikit-learn")
