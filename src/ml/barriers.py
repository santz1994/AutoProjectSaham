"""
Triple-Barrier Labeling Method (Lopez de Prado, 2018)

A more sophisticated labeling approach that considers:
1. Take-profit barrier (upper limit)
2. Stop-loss barrier (lower limit)
3. Time horizon barrier (maximum holding period)

Label is determined by which barrier is hit first:
- Label 1: Take-profit hit first (profitable trade)
- Label -1: Stop-loss hit first (losing trade)
- Label 0: Time horizon reached first (timeout/neutral)

This method produces more realistic labels for trading strategies
by accounting for both profit targets and risk management.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from typing import Tuple, Optional


class TripleBarrierLabeler:
    """
    Triple-barrier method for financial time series labeling.
    
    Attributes:
        take_profit: Target profit threshold (e.g., 0.03 = 3%)
        stop_loss: Maximum loss threshold (e.g., 0.02 = 2%)
        max_horizon: Maximum holding period in bars
    """
    
    def __init__(
        self, 
        take_profit: float = 0.03, 
        stop_loss: float = 0.02, 
        max_horizon: int = 5
    ):
        """
        Initialize triple-barrier labeler.
        
        Args:
            take_profit: Profit target as fraction (e.g., 0.03 = 3%)
            stop_loss: Stop loss as fraction (e.g., 0.02 = 2%)
            max_horizon: Maximum bars to hold before timeout
        """
        if take_profit <= 0:
            raise ValueError("take_profit must be positive")
        if stop_loss <= 0:
            raise ValueError("stop_loss must be positive")
        if max_horizon < 1:
            raise ValueError("max_horizon must be >= 1")
            
        self.take_profit = take_profit
        self.stop_loss = stop_loss
        self.max_horizon = max_horizon
    
    def apply_barriers(
        self, 
        prices: np.ndarray, 
        t: int
    ) -> Tuple[int, int, float]:
        """
        Apply triple barriers starting at time t.
        
        Args:
            prices: Price array (1D numpy array)
            t: Current time index
            
        Returns:
            Tuple of (label, bars_to_exit, actual_return):
            - label: 1 (profit), -1 (loss), 0 (timeout)
            - bars_to_exit: Number of bars until barrier hit
            - actual_return: Actual return when barrier hit
        """
        if t < 0 or t >= len(prices):
            raise IndexError(f"Invalid time index t={t} for prices length {len(prices)}")
        
        entry_price = prices[t]
        upper_barrier = entry_price * (1 + self.take_profit)
        lower_barrier = entry_price * (1 - self.stop_loss)
        
        # Scan forward up to max_horizon
        end_idx = min(t + self.max_horizon, len(prices) - 1)
        
        for i in range(t + 1, end_idx + 1):
            current_price = prices[i]
            
            # Check take-profit barrier
            if current_price >= upper_barrier:
                bars_to_exit = i - t
                actual_return = (current_price / entry_price) - 1.0
                return (1, bars_to_exit, actual_return)
            
            # Check stop-loss barrier
            if current_price <= lower_barrier:
                bars_to_exit = i - t
                actual_return = (current_price / entry_price) - 1.0
                return (-1, bars_to_exit, actual_return)
        
        # Time horizon reached without hitting profit/loss barriers
        exit_price = prices[end_idx]
        bars_to_exit = end_idx - t
        actual_return = (exit_price / entry_price) - 1.0
        
        # Classify timeout based on actual return
        if actual_return > 0.005:  # Small positive threshold (0.5%)
            label = 1
        elif actual_return < -0.005:  # Small negative threshold
            label = -1
        else:
            label = 0  # Neutral
        
        return (label, bars_to_exit, actual_return)
    
    def label_series(
        self, 
        prices: np.ndarray, 
        min_observations: int = 20
    ) -> pd.DataFrame:
        """
        Label entire price series using triple-barrier method.
        
        Args:
            prices: Price array (1D numpy array)
            min_observations: Minimum history required before labeling
            
        Returns:
            DataFrame with columns:
            - t_index: Time index
            - label: 1 (profit), -1 (loss), 0 (neutral)
            - bars_to_exit: Holding period
            - actual_return: Realized return
            - entry_price: Entry price
        """
        if len(prices) < min_observations + self.max_horizon:
            raise ValueError(
                f"Insufficient data: need at least {min_observations + self.max_horizon} bars"
            )
        
        results = []
        
        # Start labeling after min_observations
        for t in range(min_observations, len(prices) - self.max_horizon):
            label, bars, ret = self.apply_barriers(prices, t)
            
            results.append({
                't_index': t,
                'label': label,
                'bars_to_exit': bars,
                'actual_return': ret,
                'entry_price': prices[t]
            })
        
        return pd.DataFrame(results)


class MetaLabeler:
    """
    Meta-labeling: Use ML to predict probability that primary model is correct.
    
    Instead of predicting direction (up/down), predict whether a given signal
    will be profitable. This allows for better position sizing and trade filtering.
    
    Reference: Lopez de Prado (2018), "Advances in Financial Machine Learning"
    """
    
    def __init__(
        self, 
        primary_labels: np.ndarray, 
        barrier_results: pd.DataFrame
    ):
        """
        Initialize meta-labeler.
        
        Args:
            primary_labels: Labels from primary model (e.g., ML predictions)
            barrier_results: Results from triple-barrier labeling
        """
        self.primary_labels = primary_labels
        self.barrier_results = barrier_results
    
    def create_meta_labels(self) -> np.ndarray:
        """
        Create binary meta-labels: 1 if primary prediction was correct, 0 otherwise.
        
        Returns:
            Binary array indicating if primary model was correct
        """
        # Meta-label is 1 when primary prediction matches barrier outcome
        meta_labels = np.zeros(len(self.primary_labels), dtype=int)
        
        for i, (primary, actual) in enumerate(
            zip(self.primary_labels, self.barrier_results['label'])
        ):
            # If primary predicted positive and actual was positive
            if primary > 0 and actual > 0:
                meta_labels[i] = 1
            # If primary predicted negative and actual was negative
            elif primary < 0 and actual < 0:
                meta_labels[i] = 1
            # If primary predicted neutral and actual was neutral
            elif primary == 0 and actual == 0:
                meta_labels[i] = 1
            # Otherwise, primary was wrong
            else:
                meta_labels[i] = 0
        
        return meta_labels


def fractional_differentiation(
    series: np.ndarray, 
    d: float = 0.5, 
    threshold: float = 1e-5
) -> np.ndarray:
    """
    Apply fractional differentiation to make series stationary while preserving memory.
    
    Traditional differencing (d=1) removes all memory. Fractional differentiation
    with 0 < d < 1 achieves stationarity while retaining some memory.
    
    Args:
        series: Input time series
        d: Differentiation order (0 < d < 1 for fractional)
        threshold: Weight threshold for truncation
        
    Returns:
        Fractionally differentiated series
    """
    if not 0 < d < 1:
        raise ValueError("d must be between 0 and 1 for fractional differentiation")
    
    # Compute weights
    weights = [1.0]
    k = 1
    while True:
        weight = -weights[-1] * (d - k + 1) / k
        if abs(weight) < threshold:
            break
        weights.append(weight)
        k += 1
    
    weights = np.array(weights[::-1])  # Reverse for convolution
    
    # Apply weights via convolution
    result = np.convolve(series, weights, mode='valid')
    
    # Pad beginning with NaN
    padded = np.full(len(series), np.nan)
    padded[len(weights)-1:] = result
    
    return padded


def get_sample_weights_time_decay(
    num_samples: int, 
    decay_factor: float = 0.95
) -> np.ndarray:
    """
    Generate exponentially decaying sample weights.
    
    Recent samples get higher weight for model training, reflecting
    the assumption that recent market behavior is more relevant.
    
    Args:
        num_samples: Number of samples
        decay_factor: Decay rate (0 < decay < 1). Higher = slower decay
        
    Returns:
        Array of sample weights (normalized to sum to num_samples)
    """
    if not 0 < decay_factor < 1:
        raise ValueError("decay_factor must be between 0 and 1")
    
    # Generate exponential decay
    time_indices = np.arange(num_samples)
    weights = decay_factor ** (num_samples - 1 - time_indices)
    
    # Normalize so that sum = num_samples (for compatibility with sklearn)
    weights = weights * (num_samples / weights.sum())
    
    return weights


def get_sample_weights_by_return(
    returns: np.ndarray, 
    absolute: bool = True
) -> np.ndarray:
    """
    Generate sample weights based on absolute return magnitude.
    
    Samples with larger price moves get higher weights, as they
    contain more information about market dynamics.
    
    Args:
        returns: Array of returns
        absolute: If True, use absolute returns. If False, use raw returns
        
    Returns:
        Array of sample weights (normalized)
    """
    if absolute:
        weights = np.abs(returns)
    else:
        weights = returns
    
    # Avoid division by zero
    if weights.sum() == 0:
        return np.ones_like(weights) / len(weights)
    
    # Normalize
    weights = weights / weights.sum()
    weights = weights * len(weights)  # Scale to match sklearn convention
    
    return weights


if __name__ == "__main__":
    # Example usage
    np.random.seed(42)
    
    # Generate synthetic price series (random walk with drift)
    returns = np.random.normal(0.001, 0.02, 1000)
    prices = 100 * np.exp(np.cumsum(returns))
    
    print("=== Triple-Barrier Labeling Example ===\n")
    
    # Initialize labeler
    labeler = TripleBarrierLabeler(
        take_profit=0.03,  # 3% profit target
        stop_loss=0.02,    # 2% stop loss
        max_horizon=5      # 5 bars max
    )
    
    # Label a single point
    t = 500
    label, bars, ret = labeler.apply_barriers(prices, t)
    print(f"Single point labeling at t={t}:")
    print(f"  Entry price: ${prices[t]:.2f}")
    print(f"  Label: {label} ({'profit' if label == 1 else 'loss' if label == -1 else 'neutral'})")
    print(f"  Bars to exit: {bars}")
    print(f"  Actual return: {ret:.4f} ({ret*100:.2f}%)")
    print()
    
    # Label entire series
    df_labels = labeler.label_series(prices, min_observations=20)
    
    print(f"Series labeling results:")
    print(f"  Total labels: {len(df_labels)}")
    print(f"  Profit labels (1): {(df_labels['label'] == 1).sum()} ({(df_labels['label'] == 1).mean()*100:.1f}%)")
    print(f"  Loss labels (-1): {(df_labels['label'] == -1).sum()} ({(df_labels['label'] == -1).mean()*100:.1f}%)")
    print(f"  Neutral labels (0): {(df_labels['label'] == 0).sum()} ({(df_labels['label'] == 0).mean()*100:.1f}%)")
    print(f"  Avg bars to exit: {df_labels['bars_to_exit'].mean():.2f}")
    print(f"  Avg return: {df_labels['actual_return'].mean():.4f} ({df_labels['actual_return'].mean()*100:.2f}%)")
    print()
    
    # Time-decay weights
    weights_time = get_sample_weights_time_decay(len(df_labels), decay_factor=0.95)
    print(f"Time-decay weights:")
    print(f"  First 5 weights: {weights_time[:5]}")
    print(f"  Last 5 weights: {weights_time[-5:]}")
    print(f"  Ratio (last/first): {weights_time[-1]/weights_time[0]:.2f}x")
