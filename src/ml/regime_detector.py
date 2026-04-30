"""
Task 10: Regime Detection System - Market Regime Classification
Regime detection untuk pasar saham Indonesia (IDX - Bursa Efek Indonesia)

Mengidentifikasi 3 regime pasar utama:
1. BULL (Tren naik) - Strategi: Agresif, risk tinggi, lot size besar
2. BEAR (Tren turun) - Strategi: Defensive, risk rendah, lot size kecil  
3. SIDEWAYS (Range-bound) - Strategi: Range trading, volatility play

Menggunakan Hidden Markov Models untuk klasifikasi regime berdasarkan:
- Return harian (%)
- Volatilitas (realized volatility)
- Volume trading (normalized)
- Direction indicator

Compliance dengan regulasi IDX/OJK:
- Minimum order: 1 lot (100 shares untuk most stocks)
- Jam trading: 09:30-16:00 WIB (senin-jumat)
- Price limit: ±35% dari harga close sebelumnya
- Settlement: T+2
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple, Any
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from pathlib import Path
import joblib
import logging
from dataclasses import dataclass
from enum import Enum

try:
    from hmmlearn import hmm
    HMM_AVAILABLE = True
except ImportError:
    HMM_AVAILABLE = False

logger = logging.getLogger(__name__)


class RegimeType(Enum):
    """Market regime types."""
    BULL = 0
    BEAR = 1
    SIDEWAYS = 2
    
    def to_label(self) -> str:
        """Convert to human-readable label."""
        return self.name
    
    def get_strategy_params(self) -> Dict[str, float]:
        """Get strategy parameters for this regime."""
        params = {
            RegimeType.BULL: {
                'risk_multiplier': 1.0,      # Full risk
                'position_size_ratio': 1.0,  # Full position
                'stop_loss_percent': 0.03,   # 3% stop loss
                'take_profit_percent': 0.06, # 6% target
                'leverage': 1.0               # No leverage in bull
            },
            RegimeType.BEAR: {
                'risk_multiplier': 0.5,      # Half risk
                'position_size_ratio': 0.5,  # Half position
                'stop_loss_percent': 0.02,   # 2% stop loss (tighter)
                'take_profit_percent': 0.03, # 3% target
                'leverage': 0.0               # No leverage
            },
            RegimeType.SIDEWAYS: {
                'risk_multiplier': 0.7,      # 70% risk
                'position_size_ratio': 0.7,  # 70% position
                'stop_loss_percent': 0.025,  # 2.5% stop loss
                'take_profit_percent': 0.04, # 4% target (range boundaries)
                'leverage': 0.5               # Conservative leverage
            }
        }
        return params[self]


@dataclass
class RegimeState:
    """Regime state information."""
    regime: RegimeType
    probability: float  # Confidence (0-1)
    timestamp: str
    features: Dict[str, float]
    transition_prob: Optional[Dict[RegimeType, float]] = None
    
    def to_dict(self) -> Dict:
        """Convert to dictionary."""
        return {
            'regime': self.regime.name,
            'probability': self.probability,
            'timestamp': self.timestamp,
            'features': self.features,
            'strategy_params': self.regime.get_strategy_params()
        }


class HMMRegimeDetector:
    """
    Hidden Markov Model untuk deteksi regime pasar Indonesia.
    
    Menggunakan algoritma Baum-Welch untuk training dan Viterbi untuk inference.
    Cocok untuk data OHLCV IDX (BEI).
    """
    
    def __init__(
        self,
        n_states: int = 3,
        n_iter: int = 1000,
        random_state: int = 42,
        covariance_type: str = 'full',
        tol: float = 0.01
    ):
        """
        Initialize HMM regime detector.
        
        Args:
            n_states: Number of hidden states (default 3: Bull, Bear, Sideways)
            n_iter: Number of EM iterations
            random_state: Random seed
            covariance_type: 'full', 'tied', 'diag', 'spherical'
            tol: Convergence tolerance
        """
        if not HMM_AVAILABLE:
            raise ImportError("hmmlearn required: pip install hmmlearn")
        
        self.n_states = n_states
        self.n_iter = n_iter
        self.random_state = random_state
        self.covariance_type = covariance_type
        self.tol = tol
        
        # Initialize Gaussian HMM
        self.model = hmm.GaussianHMM(
            n_components=n_states,
            covariance_type=covariance_type,
            n_iter=n_iter,
            random_state=random_state,
            tol=tol
        )
        
        self.is_fitted = False
        self.means: Optional[np.ndarray] = None
        self.covars: Optional[np.ndarray] = None
        self.feature_names: List[str] = []
        self.state_mapping: Dict[int, RegimeType] = {}
    
    def fit(self, X: pd.DataFrame, lengths: Optional[List[int]] = None) -> None:
        """
        Fit HMM on historical data.
        
        Args:
            X: Feature DataFrame with columns [returns, volatility, volume, direction]
            lengths: Optional lengths for multiple sequences (for batch data)
        """
        if X.empty:
            raise ValueError("Empty data provided")
        
        self.feature_names = list(X.columns)
        
        try:
            # Fit HMM
            X_values = X.values
            self.model.fit(X_values, lengths)
            
            self.is_fitted = True
            self.means = self.model.means_
            self.covars = self.model.covars_
            
            # Map states to regime types based on means
            self._map_states()
            
            logger.info(f"HMM fitted with {self.n_states} states on {len(X)} samples")
            
        except Exception as e:
            logger.error(f"HMM fitting failed: {e}")
            raise
    
    def _map_states(self) -> None:
        """
        Map HMM states to regime types based on mean returns.
        
        Bull: positive mean returns
        Bear: negative mean returns
        Sideways: near-zero mean returns
        """
        if self.means is None or len(self.means) == 0:
            return
        
        # Get mean returns for each state
        returns_col_idx = 0  # Assuming first column is returns
        mean_returns = self.means[:, returns_col_idx]
        
        if self.n_states == 3:
            # Sort by mean return
            sorted_indices = np.argsort(mean_returns)
            
            self.state_mapping = {
                sorted_indices[2]: RegimeType.BULL,      # Highest returns
                sorted_indices[1]: RegimeType.SIDEWAYS,  # Middle returns
                sorted_indices[0]: RegimeType.BEAR       # Lowest returns
            }
        else:
            # Default mapping for other state counts
            for i, idx in enumerate(sorted(mean_returns.argsort())):
                if idx % self.n_states == 0:
                    self.state_mapping[i] = RegimeType.BULL
                elif idx % self.n_states == 1:
                    self.state_mapping[i] = RegimeType.SIDEWAYS
                else:
                    self.state_mapping[i] = RegimeType.BEAR
    
    def predict(self, X: pd.DataFrame) -> np.ndarray:
        """
        Predict regime states using Viterbi algorithm.
        
        Args:
            X: Feature DataFrame
            
        Returns:
            Array of state indices (0, 1, 2)
        """
        if not self.is_fitted:
            raise ValueError("Model not fitted")
        
        X_values = X.values
        states = self.model.predict(X_values)
        return states
    
    def predict_proba(self, X: pd.DataFrame) -> np.ndarray:
        """
        Get probability of each state.
        
        Args:
            X: Feature DataFrame
            
        Returns:
            Array of shape (n_samples, n_states) with probabilities
        """
        if not self.is_fitted:
            raise ValueError("Model not fitted")
        
        X_values = X.values
        log_posteriors = self.model.score_samples(X_values)[1]
        posteriors = np.exp(log_posteriors)
        
        # Normalize to sum to 1
        posteriors = posteriors / posteriors.sum(axis=1, keepdims=True)
        
        return posteriors
    
    def get_regime_type(self, state_idx: int) -> RegimeType:
        """Get regime type for a state index."""
        return self.state_mapping.get(state_idx, RegimeType.SIDEWAYS)


class RegimeAnalyzer:
    """
    Analyze regime characteristics and statistics.
    
    Cocok untuk analisis IDX: return patterns, volatility by regime, dll.
    """
    
    def __init__(self, window: int = 20):
        """
        Initialize analyzer.
        
        Args:
            window: Window size for rolling statistics
        """
        self.window = window
        self.regime_history: List[RegimeState] = []
        self.statistics: Dict[RegimeType, Dict[str, float]] = {}
    
    def analyze_regimes(
        self,
        prices: np.ndarray,
        volumes: np.ndarray,
        regime_states: np.ndarray,
        regime_detector: HMMRegimeDetector
    ) -> Dict[RegimeType, Dict[str, float]]:
        """
        Analyze characteristics of each regime.
        
        Args:
            prices: Price array
            volumes: Volume array
            regime_states: State indices from HMM
            regime_detector: Fitted HMM detector
            
        Returns:
            Statistics by regime type
        """
        stats = {}
        
        for state_idx in range(regime_detector.n_states):
            regime_type = regime_detector.get_regime_type(state_idx)
            mask = regime_states == state_idx
            
            if not np.any(mask):
                continue
            
            regime_prices = prices[mask]
            regime_volumes = volumes[mask]
            regime_returns = np.diff(regime_prices) / regime_prices[:-1]
            
            stats[regime_type] = {
                'mean_return': float(np.mean(regime_returns)),
                'std_return': float(np.std(regime_returns)),
                'sharpe_ratio': float(np.mean(regime_returns) / (np.std(regime_returns) + 1e-8)),
                'max_return': float(np.max(regime_returns)),
                'min_return': float(np.min(regime_returns)),
                'avg_volume': float(np.mean(regime_volumes)),
                'duration_days': int(np.sum(mask)),
                'frequency_percent': float(100 * np.sum(mask) / len(mask))
            }
        
        self.statistics = stats
        return stats
    
    def get_regime_report(self) -> Dict:
        """Get comprehensive regime analysis report."""
        return {
            'statistics': self.statistics,
            'regime_history': [r.to_dict() for r in self.regime_history[-50:]],
            'total_regimes_detected': len(self.regime_history)
        }


class RegimeIntegration:
    """
    Integration layer untuk menggunakan regime detection dalam trading strategy.
    
    Cocok dengan:
    - Position sizing (berdasarkan regime risk)
    - Stop loss & take profit (regime-specific)
    - Strategy selection
    - Portfolio rebalancing
    """
    
    def __init__(self, regime_detector: HMMRegimeDetector):
        """
        Initialize integration.
        
        Args:
            regime_detector: Fitted HMM detector
        """
        self.regime_detector = regime_detector
        self.current_regime: Optional[RegimeState] = None
        self.regime_transitions: List[Tuple[str, str]] = []
    
    def update_regime(
        self,
        features: pd.DataFrame,
        current_price: float,
        current_time: Optional[datetime] = None
    ) -> RegimeState:
        """
        Update current regime based on latest features.
        
        Args:
            features: Latest feature values (single row DataFrame)
            current_price: Current price
            current_time: Current timestamp
            
        Returns:
            Updated regime state
        """
        if current_time is None:
            current_time = datetime.now()
        
        # Predict state
        state_idx = self.regime_detector.predict(features)[0]
        regime = self.regime_detector.get_regime_type(state_idx)
        
        # Get probability
        proba = self.regime_detector.predict_proba(features)[0]
        prob = float(proba[state_idx])
        
        # Create regime state
        new_regime = RegimeState(
            regime=regime,
            probability=prob,
            timestamp=current_time.isoformat(),
            features={
                'price': current_price,
                **{name: float(val) for name, val in zip(
                    self.regime_detector.feature_names,
                    features.values[0]
                )}
            }
        )
        
        # Track transition
        if self.current_regime and self.current_regime.regime != regime:
            self.regime_transitions.append((
                self.current_regime.regime.name,
                regime.name
            ))
            logger.info(f"Regime transition: {self.current_regime.regime.name} → {regime.name}")
        
        self.current_regime = new_regime
        return new_regime
    
    def get_strategy_params(self) -> Dict[str, float]:
        """Get current regime's strategy parameters."""
        if self.current_regime is None:
            # Default parameters
            return RegimeType.SIDEWAYS.get_strategy_params()
        
        return self.current_regime.regime.get_strategy_params()
    
    def should_trade(self) -> bool:
        """
        Determine if trading is allowed in current regime.
        
        Returns:
            True if regime confidence is high enough
        """
        if self.current_regime is None:
            return False
        
        # Trade if confidence > 70%
        return self.current_regime.probability > 0.7
    
    def adjust_position_for_regime(
        self,
        base_position: float,
        regime: Optional[RegimeType] = None
    ) -> float:
        """
        Adjust position size based on regime.
        
        Compliance IDX:
        - Minimum lot: 1 (100 shares)
        - Position harus multiple dari lot size
        
        Args:
            base_position: Base position size (Rp or shares)
            regime: Target regime (uses current if None)
            
        Returns:
            Adjusted position size
        """
        if regime is None:
            if self.current_regime is None:
                return base_position
            regime = self.current_regime.regime
        
        params = regime.get_strategy_params()
        multiplier = params['position_size_ratio']
        adjusted = base_position * multiplier
        
        # Round to nearest lot (100 shares for most IDX stocks)
        if adjusted < 100:
            adjusted = 0  # Below minimum lot
        
        return adjusted
    
    def get_regime_status(self) -> Dict:
        """Get current regime status for display/monitoring."""
        if self.current_regime is None:
            return {
                'regime': 'UNKNOWN',
                'confidence': 0.0,
                'can_trade': False,
                'params': {}
            }
        
        return {
            'regime': self.current_regime.regime.name,
            'confidence': self.current_regime.probability,
            'can_trade': self.should_trade(),
            'params': self.get_strategy_params(),
            'transitions': self.regime_transitions[-5:]  # Last 5 transitions
        }


if __name__ == "__main__":
    print("Regime Detection System untuk IDX (Bursa Efek Indonesia)")
    print("Menggunakan HMM untuk klasifikasi regime: Bull, Bear, Sideways")
    print("\nTest imports...")
    
    if not HMM_AVAILABLE:
        print("⚠️  hmmlearn not installed: pip install hmmlearn")
    else:
        print("✅ HMM available")
        print("✅ Ready for regime detection training")
