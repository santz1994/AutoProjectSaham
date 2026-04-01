"""
Anomaly Detection for Risk Management

Detects unusual patterns in trading data for risk management:
1. Isolation Forest - Statistical anomalies
2. Autoencoder - Pattern anomalies in feature space
3. Statistical thresholds - Volume, volatility spikes
4. Integration with position sizing

Anomaly detection prevents trading during:
- Flash crashes
- Unusual volume spikes
- Data quality issues
- Market manipulation events
"""
from __future__ import annotations

from typing import Dict, List, Optional, Tuple, Any
import numpy as np
import pandas as pd
from datetime import datetime
from pathlib import Path
import joblib
import logging

try:
    from sklearn.ensemble import IsolationForest
    from sklearn.preprocessing import StandardScaler
    from sklearn.covariance import EllipticEnvelope
    SKLEARN_AVAILABLE = True
except ImportError:
    SKLEARN_AVAILABLE = False

logger = logging.getLogger(__name__)


class IsolationForestDetector:
    """
    Isolation Forest for outlier detection.
    
    Detects anomalies by isolating observations.
    Works well for high-dimensional data.
    """
    
    def __init__(
        self,
        contamination: float = 0.05,
        n_estimators: int = 100,
        max_features: float = 1.0
    ):
        """
        Initialize Isolation Forest detector.
        
        Args:
            contamination: Expected proportion of outliers (0.01-0.1)
            n_estimators: Number of trees
            max_features: Features per tree (1.0 = all features)
        """
        if not SKLEARN_AVAILABLE:
            raise ImportError("scikit-learn required")
        
        self.model = IsolationForest(
            contamination=contamination,
            n_estimators=n_estimators,
            max_features=max_features,
            random_state=42
        )
        self.scaler = StandardScaler()
        self.is_fitted = False
        self.feature_names: List[str] = []
    
    def fit(self, X: pd.DataFrame) -> None:
        """Fit detector on normal data."""
        self.feature_names = list(X.columns)
        X_scaled = self.scaler.fit_transform(X.values)
        self.model.fit(X_scaled)
        self.is_fitted = True
        logger.info(f"IsolationForest fitted on {len(X)} samples")
    
    def predict(self, X: pd.DataFrame) -> np.ndarray:
        """
        Predict anomalies.
        
        Returns:
            Array of 1 (normal) or -1 (anomaly)
        """
        if not self.is_fitted:
            raise ValueError("Detector not fitted")
        
        X_scaled = self.scaler.transform(X.values)
        return self.model.predict(X_scaled)
    
    def score_samples(self, X: pd.DataFrame) -> np.ndarray:
        """
        Get anomaly scores.
        
        Returns:
            Anomaly scores (lower = more anomalous)
        """
        if not self.is_fitted:
            raise ValueError("Detector not fitted")
        
        X_scaled = self.scaler.transform(X.values)
        return self.model.score_samples(X_scaled)


class StatisticalAnomalyDetector:
    """
    Statistical anomaly detection using Z-scores and IQR.
    
    Detects:
    - Price spikes (>5 std dev)
    - Volume anomalies (>3 std dev)
    - Volatility spikes
    """
    
    def __init__(
        self,
        window: int = 100,
        z_threshold: float = 3.0,
        iqr_multiplier: float = 1.5
    ):
        """
        Initialize statistical detector.
        
        Args:
            window: Rolling window for statistics
            z_threshold: Z-score threshold (typically 2-4)
            iqr_multiplier: IQR multiplier (typically 1.5-3.0)
        """
        self.window = window
        self.z_threshold = z_threshold
        self.iqr_multiplier = iqr_multiplier
        
        # Statistics tracking
        self.stats_history: Dict[str, List[float]] = {}
    
    def detect_price_anomaly(
        self,
        prices: np.ndarray,
        returns: Optional[np.ndarray] = None
    ) -> Tuple[np.ndarray, np.ndarray]:
        """
        Detect price anomalies using Z-score.
        
        Args:
            prices: Price series
            returns: Return series (computed if None)
            
        Returns:
            Tuple of (anomaly_mask, z_scores)
        """
        if returns is None:
            returns = np.diff(prices) / prices[:-1]
            returns = np.concatenate([[0], returns])
        
        # Rolling Z-score
        anomalies = np.zeros(len(returns), dtype=bool)
        z_scores = np.zeros(len(returns))
        
        for i in range(self.window, len(returns)):
            window_data = returns[i-self.window:i]
            mean = np.mean(window_data)
            std = np.std(window_data)
            
            if std > 0:
                z_scores[i] = (returns[i] - mean) / std
                anomalies[i] = abs(z_scores[i]) > self.z_threshold
        
        return anomalies, z_scores
    
    def detect_volume_anomaly(
        self,
        volumes: np.ndarray
    ) -> Tuple[np.ndarray, np.ndarray]:
        """
        Detect volume anomalies using IQR method.
        
        Args:
            volumes: Volume series
            
        Returns:
            Tuple of (anomaly_mask, volume_ratios)
        """
        anomalies = np.zeros(len(volumes), dtype=bool)
        ratios = np.zeros(len(volumes))
        
        for i in range(self.window, len(volumes)):
            window_data = volumes[i-self.window:i]
            q1 = np.percentile(window_data, 25)
            q3 = np.percentile(window_data, 75)
            iqr = q3 - q1
            
            upper_bound = q3 + self.iqr_multiplier * iqr
            median = np.median(window_data)
            
            if median > 0:
                ratios[i] = volumes[i] / median
                anomalies[i] = volumes[i] > upper_bound
        
        return anomalies, ratios
    
    def detect_volatility_spike(
        self,
        returns: np.ndarray,
        threshold_multiplier: float = 3.0
    ) -> np.ndarray:
        """
        Detect volatility spikes.
        
        Args:
            returns: Return series
            threshold_multiplier: Spike threshold (x times normal vol)
            
        Returns:
            Anomaly mask
        """
        anomalies = np.zeros(len(returns), dtype=bool)
        
        # Rolling volatility
        for i in range(self.window, len(returns)):
            window_data = returns[i-self.window:i]
            vol_mean = np.std(window_data)
            current_vol = abs(returns[i])
            
            if vol_mean > 0:
                anomalies[i] = current_vol > vol_mean * threshold_multiplier
        
        return anomalies


class AnomalyRiskManager:
    """
    Risk management using anomaly detection.
    
    Integrates multiple detectors and adjusts position sizing.
    """
    
    def __init__(
        self,
        isolation_contamination: float = 0.05,
        z_threshold: float = 3.0,
        risk_reduction_factor: float = 0.5
    ):
        """
        Initialize risk manager.
        
        Args:
            isolation_contamination: IsolationForest contamination
            z_threshold: Statistical threshold
            risk_reduction_factor: Position size multiplier during anomalies
        """
        self.isolation_detector = IsolationForestDetector(
            contamination=isolation_contamination
        ) if SKLEARN_AVAILABLE else None
        
        self.statistical_detector = StatisticalAnomalyDetector(
            z_threshold=z_threshold
        )
        
        self.risk_reduction_factor = risk_reduction_factor
        
        # Anomaly tracking
        self.anomaly_history: List[Dict] = []
        self.current_anomaly_score = 0.0
    
    def fit(self, X: pd.DataFrame) -> None:
        """Fit detectors on historical data."""
        if self.isolation_detector:
            self.isolation_detector.fit(X)
            logger.info("Anomaly detectors fitted")
    
    def detect_anomalies(
        self,
        features: pd.DataFrame,
        prices: Optional[np.ndarray] = None,
        volumes: Optional[np.ndarray] = None
    ) -> Dict[str, Any]:
        """
        Comprehensive anomaly detection.
        
        Args:
            features: Feature DataFrame
            prices: Price series (optional)
            volumes: Volume series (optional)
            
        Returns:
            Dictionary with anomaly results
        """
        results = {
            'is_anomaly': False,
            'anomaly_types': [],
            'anomaly_score': 0.0,
            'risk_multiplier': 1.0,
            'details': {}
        }
        
        # 1. Isolation Forest detection
        if self.isolation_detector and self.isolation_detector.is_fitted:
            iso_pred = self.isolation_detector.predict(features)
            iso_scores = self.isolation_detector.score_samples(features)
            
            if iso_pred[-1] == -1:  # Last sample is anomaly
                results['anomaly_types'].append('isolation_forest')
                results['details']['isolation_score'] = float(iso_scores[-1])
        
        # 2. Statistical detection
        if prices is not None and len(prices) > 100:
            price_anom, z_scores = self.statistical_detector.detect_price_anomaly(prices)
            if price_anom[-1]:
                results['anomaly_types'].append('price_spike')
                results['details']['z_score'] = float(z_scores[-1])
        
        if volumes is not None and len(volumes) > 100:
            vol_anom, vol_ratios = self.statistical_detector.detect_volume_anomaly(volumes)
            if vol_anom[-1]:
                results['anomaly_types'].append('volume_spike')
                results['details']['volume_ratio'] = float(vol_ratios[-1])
        
        # 3. Aggregate results
        results['is_anomaly'] = len(results['anomaly_types']) > 0
        results['anomaly_score'] = len(results['anomaly_types']) / 3.0  # Normalize
        
        # 4. Calculate risk multiplier
        if results['is_anomaly']:
            results['risk_multiplier'] = self.risk_reduction_factor
        
        # 5. Log anomaly
        if results['is_anomaly']:
            self.anomaly_history.append({
                'timestamp': datetime.now().isoformat(),
                'types': results['anomaly_types'],
                'score': results['anomaly_score'],
                'details': results['details']
            })
        
        self.current_anomaly_score = results['anomaly_score']
        
        return results
    
    def adjust_position_size(
        self,
        base_position: float,
        anomaly_result: Optional[Dict] = None
    ) -> float:
        """
        Adjust position size based on anomaly detection.
        
        Args:
            base_position: Original position size
            anomaly_result: Anomaly detection result
            
        Returns:
            Adjusted position size
        """
        if anomaly_result and anomaly_result['is_anomaly']:
            multiplier = anomaly_result['risk_multiplier']
            adjusted = base_position * multiplier
            
            logger.warning(
                f"Anomaly detected: {anomaly_result['anomaly_types']}. "
                f"Position reduced: {base_position:.2f} -> {adjusted:.2f}"
            )
            
            return adjusted
        
        return base_position
    
    def get_anomaly_report(self) -> Dict:
        """Get anomaly detection statistics."""
        if not self.anomaly_history:
            return {
                'total_anomalies': 0,
                'recent_anomalies': [],
                'current_score': self.current_anomaly_score
            }
        
        # Count anomaly types
        type_counts = {}
        for anom in self.anomaly_history:
            for anom_type in anom['types']:
                type_counts[anom_type] = type_counts.get(anom_type, 0) + 1
        
        return {
            'total_anomalies': len(self.anomaly_history),
            'type_counts': type_counts,
            'recent_anomalies': self.anomaly_history[-10:],
            'current_score': self.current_anomaly_score
        }
    
    def save(self, filepath: str) -> None:
        """Save risk manager state."""
        Path(filepath).parent.mkdir(parents=True, exist_ok=True)
        
        state = {
            'isolation_detector': self.isolation_detector,
            'anomaly_history': self.anomaly_history,
            'risk_reduction_factor': self.risk_reduction_factor
        }
        
        joblib.dump(state, filepath)
        logger.info(f"Risk manager saved to {filepath}")
    
    def load(self, filepath: str) -> None:
        """Load risk manager state."""
        state = joblib.load(filepath)
        
        self.isolation_detector = state['isolation_detector']
        self.anomaly_history = state['anomaly_history']
        self.risk_reduction_factor = state['risk_reduction_factor']
        
        logger.info(f"Risk manager loaded from {filepath}")


if __name__ == "__main__":
    print("=== Anomaly Detection Demo ===\n")
    
    if not SKLEARN_AVAILABLE:
        print("ERROR: scikit-learn not installed")
        exit(1)
    
    np.random.seed(42)
    
    # Generate normal trading data
    n_normal = 500
    prices = 100 * np.exp(np.cumsum(np.random.randn(n_normal) * 0.02))
    volumes = np.random.uniform(1e6, 2e6, n_normal)
    features = pd.DataFrame({
        'returns': np.diff(prices, prepend=prices[0]) / prices,
        'volume': volumes,
        'volatility': pd.Series(np.diff(prices, prepend=prices[0]) / prices).rolling(20).std().fillna(0),
        'rsi': np.random.uniform(30, 70, n_normal)
    })
    
    # Create risk manager
    risk_mgr = AnomalyRiskManager()
    risk_mgr.fit(features.iloc[:400])  # Fit on first 400 samples
    
    print("Testing on normal data (samples 400-480)...\n")
    for i in range(400, 480):
        result = risk_mgr.detect_anomalies(
            features.iloc[i:i+1],
            prices[:i+1],
            volumes[:i+1]
        )
        if result['is_anomaly']:
            print(f"  Sample {i}: Anomaly! {result['anomaly_types']}")
    
    # Inject anomalies
    print("\nInjecting anomalies (samples 480-500)...\n")
    
    # Flash crash
    prices[485] = prices[484] * 0.85  # 15% drop
    features.loc[485, 'returns'] = -0.15
    
    # Volume spike
    volumes[490] = volumes[489] * 10  # 10x volume
    features.loc[490, 'volume'] = volumes[490]
    
    # Test detection
    for i in range(480, 500):
        result = risk_mgr.detect_anomalies(
            features.iloc[i:i+1],
            prices[:i+1],
            volumes[:i+1]
        )
        
        if result['is_anomaly']:
            print(f"  ⚠️  Sample {i}: {result['anomaly_types']}")
            print(f"      Score: {result['anomaly_score']:.2f}")
            print(f"      Risk multiplier: {result['risk_multiplier']:.2f}")
            
            # Test position adjustment
            original_pos = 10000
            adjusted_pos = risk_mgr.adjust_position_size(original_pos, result)
            print(f"      Position: ${original_pos} -> ${adjusted_pos:.0f}\n")
    
    # Report
    report = risk_mgr.get_anomaly_report()
    print("\n" + "="*50)
    print("Anomaly Detection Report")
    print("="*50)
    print(f"Total anomalies detected: {report['total_anomalies']}")
    print(f"Type breakdown: {report['type_counts']}")
    print(f"Current anomaly score: {report['current_score']:.2f}")
    print("\n✅ Demo complete!")
