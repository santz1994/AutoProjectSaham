"""
Market Microstructure Features

Advanced features capturing price dynamics, liquidity, and market structure:
1. VWAP deviation (volume-weighted average price)
2. Order flow imbalance (buy vs sell pressure)
3. Bid-ask spread dynamics
4. Volume profile analysis
5. Price impact estimation
6. Liquidity metrics

These features help capture short-term market dynamics
and improve prediction accuracy for intraday strategies.
"""
from __future__ import annotations

from typing import Dict, List, Optional, Tuple
import numpy as np
import pandas as pd


class MicrostructureAnalyzer:
    """
    Analyze market microstructure from OHLCV and order book data.
    
    Computes features that capture:
    - Liquidity (volume, spread, depth)
    - Order flow (buy/sell imbalance)
    - Price efficiency (VWAP deviation)
    - Market impact
    """
    
    def __init__(self):
        """Initialize microstructure analyzer."""
        pass
    
    def compute_vwap(
        self, 
        high: np.ndarray,
        low: np.ndarray,
        close: np.ndarray,
        volume: np.ndarray
    ) -> np.ndarray:
        """
        Compute Volume-Weighted Average Price (VWAP).
        
        VWAP = Σ(price * volume) / Σ(volume)
        where price = (high + low + close) / 3 (typical price)
        
        Args:
            high: High prices
            low: Low prices
            close: Close prices
            volume: Volumes
            
        Returns:
            VWAP array
        """
        typical_price = (high + low + close) / 3.0
        cum_vol_price = np.cumsum(typical_price * volume)
        cum_vol = np.cumsum(volume)
        
        # Avoid division by zero
        vwap = np.divide(
            cum_vol_price, 
            cum_vol, 
            out=np.full_like(cum_vol_price, np.nan),
            where=cum_vol != 0
        )
        
        # Forward fill NaN values
        vwap = pd.Series(vwap).fillna(method='ffill').fillna(method='bfill').values
        
        return vwap
    
    def compute_vwap_deviation(
        self,
        close: np.ndarray,
        vwap: np.ndarray
    ) -> np.ndarray:
        """
        Compute price deviation from VWAP.
        
        Deviation = (close - vwap) / vwap
        
        Positive deviation: price above VWAP (buying pressure)
        Negative deviation: price below VWAP (selling pressure)
        
        Args:
            close: Close prices
            vwap: VWAP values
            
        Returns:
            VWAP deviation array
        """
        return np.divide(
            close - vwap,
            vwap,
            out=np.zeros_like(close),
            where=vwap != 0
        )
    
    def compute_order_flow_imbalance(
        self,
        bid_volume: Optional[np.ndarray] = None,
        ask_volume: Optional[np.ndarray] = None,
        close: Optional[np.ndarray] = None,
        volume: Optional[np.ndarray] = None
    ) -> np.ndarray:
        """
        Compute order flow imbalance.
        
        Method 1 (if bid/ask volume available):
        OFI = (bid_volume - ask_volume) / (bid_volume + ask_volume)
        
        Method 2 (fallback using price changes):
        Estimate buy volume using up moves, sell volume using down moves
        
        Args:
            bid_volume: Bid side volume (optional)
            ask_volume: Ask side volume (optional)
            close: Close prices (for fallback method)
            volume: Total volume (for fallback method)
            
        Returns:
            Order flow imbalance array (-1 to 1)
        """
        if bid_volume is not None and ask_volume is not None:
            # Direct calculation from order book
            total_vol = bid_volume + ask_volume
            ofi = np.divide(
                bid_volume - ask_volume,
                total_vol,
                out=np.zeros_like(bid_volume, dtype=float),
                where=total_vol != 0
            )
        elif close is not None and volume is not None:
            # Fallback: estimate from price changes
            price_changes = np.diff(close, prepend=close[0])
            
            # Positive changes -> buy pressure, negative -> sell pressure
            buy_vol = np.where(price_changes > 0, volume, 0)
            sell_vol = np.where(price_changes < 0, volume, 0)
            
            total_vol = buy_vol + sell_vol
            ofi = np.divide(
                buy_vol - sell_vol,
                total_vol,
                out=np.zeros_like(volume, dtype=float),
                where=total_vol != 0
            )
        else:
            raise ValueError("Either (bid_volume, ask_volume) or (close, volume) must be provided")
        
        return ofi
    
    def compute_bid_ask_spread(
        self,
        bid_price: np.ndarray,
        ask_price: np.ndarray,
        mid_price: Optional[np.ndarray] = None
    ) -> Tuple[np.ndarray, np.ndarray]:
        """
        Compute bid-ask spread (absolute and relative).
        
        Args:
            bid_price: Bid prices
            ask_price: Ask prices
            mid_price: Mid prices (optional, computed as (bid + ask)/2 if None)
            
        Returns:
            Tuple of (absolute_spread, relative_spread)
            - absolute_spread: ask - bid
            - relative_spread: (ask - bid) / mid_price
        """
        absolute_spread = ask_price - bid_price
        
        if mid_price is None:
            mid_price = (bid_price + ask_price) / 2.0
        
        relative_spread = np.divide(
            absolute_spread,
            mid_price,
            out=np.zeros_like(absolute_spread),
            where=mid_price != 0
        )
        
        return absolute_spread, relative_spread
    
    def compute_volume_profile(
        self,
        prices: np.ndarray,
        volumes: np.ndarray,
        num_bins: int = 10
    ) -> Dict[str, float]:
        """
        Compute volume profile (volume distribution across price levels).
        
        Args:
            prices: Price array
            volumes: Volume array
            num_bins: Number of price bins
            
        Returns:
            Dictionary with volume profile metrics:
            - poc_price: Point of Control (price level with highest volume)
            - vah: Value Area High (top of value area)
            - val: Value Area Low (bottom of value area)
            - value_area_volume_pct: % of volume in value area
        """
        # Create price bins
        price_range = np.linspace(prices.min(), prices.max(), num_bins + 1)
        
        # Aggregate volume per bin
        bin_volumes = np.zeros(num_bins)
        bin_indices = np.digitize(prices, price_range) - 1
        bin_indices = np.clip(bin_indices, 0, num_bins - 1)
        
        for i, vol in zip(bin_indices, volumes):
            bin_volumes[i] += vol
        
        # Point of Control (highest volume bin)
        poc_idx = np.argmax(bin_volumes)
        poc_price = (price_range[poc_idx] + price_range[poc_idx + 1]) / 2.0
        
        # Value Area (70% of volume around POC)
        total_volume = volumes.sum()
        target_volume = total_volume * 0.70
        
        # Expand from POC until 70% volume reached
        value_area_indices = [poc_idx]
        value_area_volume = bin_volumes[poc_idx]
        
        left_idx = poc_idx - 1
        right_idx = poc_idx + 1
        
        while value_area_volume < target_volume and (left_idx >= 0 or right_idx < num_bins):
            # Choose side with higher volume
            left_vol = bin_volumes[left_idx] if left_idx >= 0 else 0
            right_vol = bin_volumes[right_idx] if right_idx < num_bins else 0
            
            if left_vol >= right_vol and left_idx >= 0:
                value_area_indices.append(left_idx)
                value_area_volume += left_vol
                left_idx -= 1
            elif right_idx < num_bins:
                value_area_indices.append(right_idx)
                value_area_volume += right_vol
                right_idx += 1
            else:
                break
        
        # Value Area High and Low
        value_area_indices.sort()
        vah = price_range[value_area_indices[-1] + 1]  # Upper bound of highest bin
        val = price_range[value_area_indices[0]]  # Lower bound of lowest bin
        
        return {
            'poc_price': float(poc_price),
            'vah': float(vah),
            'val': float(val),
            'value_area_volume_pct': float(value_area_volume / total_volume * 100)
        }
    
    def compute_price_impact(
        self,
        volume: np.ndarray,
        price_changes: np.ndarray,
        window: int = 5
    ) -> np.ndarray:
        """
        Estimate price impact (how much volume moves price).
        
        Impact = |price_change| / volume
        Averaged over a rolling window.
        
        Args:
            volume: Volume array
            price_changes: Price change array (absolute or %)
            window: Rolling window size
            
        Returns:
            Price impact array (higher = more illiquid)
        """
        # Price impact per bar
        impact = np.divide(
            np.abs(price_changes),
            volume,
            out=np.zeros_like(volume, dtype=float),
            where=volume != 0
        )
        
        # Rolling average
        impact_series = pd.Series(impact)
        rolling_impact = impact_series.rolling(window=window, min_periods=1).mean()
        
        return rolling_impact.values
    
    def compute_amihud_illiquidity(
        self,
        returns: np.ndarray,
        volume: np.ndarray,
        window: int = 20
    ) -> np.ndarray:
        """
        Compute Amihud illiquidity ratio.
        
        Amihud = avg(|return| / volume) over window
        
        Higher values indicate lower liquidity (price moves more per unit volume).
        
        Args:
            returns: Return array
            volume: Volume array
            window: Rolling window
            
        Returns:
            Amihud illiquidity array
        """
        # Daily illiquidity
        daily_illiq = np.divide(
            np.abs(returns),
            volume,
            out=np.zeros_like(returns),
            where=volume != 0
        )
        
        # Rolling average
        illiq_series = pd.Series(daily_illiq)
        amihud = illiq_series.rolling(window=window, min_periods=1).mean()
        
        return amihud.values


def compute_microstructure_features(
    df: pd.DataFrame,
    ofi_window: int = 5,
    impact_window: int = 5,
    illiquidity_window: int = 20
) -> pd.DataFrame:
    """
    Compute all microstructure features for a DataFrame with OHLCV data.
    
    Args:
        df: DataFrame with columns ['high', 'low', 'close', 'volume']
            Optional: ['bid', 'ask', 'bid_volume', 'ask_volume']
        ofi_window: Window for order flow imbalance smoothing
        impact_window: Window for price impact averaging
        illiquidity_window: Window for Amihud illiquidity
        
    Returns:
        DataFrame with added microstructure features
    """
    df = df.copy()
    analyzer = MicrostructureAnalyzer()
    
    # Required columns
    required = ['high', 'low', 'close', 'volume']
    if not all(col in df.columns for col in required):
        raise ValueError(f"DataFrame must contain columns: {required}")
    
    # VWAP
    vwap = analyzer.compute_vwap(
        df['high'].values,
        df['low'].values,
        df['close'].values,
        df['volume'].values
    )
    df['vwap'] = vwap
    
    # VWAP deviation
    df['vwap_deviation'] = analyzer.compute_vwap_deviation(
        df['close'].values,
        vwap
    )
    
    # Order flow imbalance
    if 'bid_volume' in df.columns and 'ask_volume' in df.columns:
        ofi = analyzer.compute_order_flow_imbalance(
            bid_volume=df['bid_volume'].values,
            ask_volume=df['ask_volume'].values
        )
    else:
        # Fallback method
        ofi = analyzer.compute_order_flow_imbalance(
            close=df['close'].values,
            volume=df['volume'].values
        )
    df['order_flow_imbalance'] = ofi
    
    # Smoothed OFI
    df['ofi_ma'] = df['order_flow_imbalance'].rolling(window=ofi_window, min_periods=1).mean()
    
    # Bid-ask spread (if available)
    if 'bid' in df.columns and 'ask' in df.columns:
        abs_spread, rel_spread = analyzer.compute_bid_ask_spread(
            df['bid'].values,
            df['ask'].values
        )
        df['bid_ask_spread'] = abs_spread
        df['relative_spread'] = rel_spread
    
    # Price impact
    returns = df['close'].pct_change().fillna(0)
    df['price_impact'] = analyzer.compute_price_impact(
        df['volume'].values,
        returns.values,
        window=impact_window
    )
    
    # Amihud illiquidity
    df['amihud_illiquidity'] = analyzer.compute_amihud_illiquidity(
        returns.values,
        df['volume'].values,
        window=illiquidity_window
    )
    
    return df


if __name__ == "__main__":
    # Example usage
    print("=== Market Microstructure Features Example ===\n")
    
    # Generate synthetic OHLCV data
    np.random.seed(42)
    n = 100
    
    close = 100 * np.exp(np.cumsum(np.random.normal(0.001, 0.02, n)))
    high = close * (1 + np.abs(np.random.normal(0, 0.01, n)))
    low = close * (1 - np.abs(np.random.normal(0, 0.01, n)))
    volume = np.random.uniform(1e6, 5e6, n)
    
    df = pd.DataFrame({
        'high': high,
        'low': low,
        'close': close,
        'volume': volume
    })
    
    # Compute features
    df_features = compute_microstructure_features(df)
    
    print("Sample features (last 5 rows):")
    print(df_features[['close', 'vwap', 'vwap_deviation', 'order_flow_imbalance', 
                       'price_impact', 'amihud_illiquidity']].tail())
    
    print(f"\n=== Feature Statistics ===")
    print(f"VWAP deviation mean: {df_features['vwap_deviation'].mean():.4f}")
    print(f"Order flow imbalance mean: {df_features['order_flow_imbalance'].mean():.4f}")
    print(f"Price impact mean: {df_features['price_impact'].mean():.6f}")
    print(f"Amihud illiquidity mean: {df_features['amihud_illiquidity'].mean():.8f}")
