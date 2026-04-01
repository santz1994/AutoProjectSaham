"""
Unit tests for triple-barrier labeling method.
"""
import unittest
import numpy as np
import pandas as pd

from src.ml.barriers import (
    TripleBarrierLabeler,
    MetaLabeler,
    fractional_differentiation,
    get_sample_weights_time_decay,
    get_sample_weights_by_return,
)


class TestTripleBarrierLabeler(unittest.TestCase):
    """Test triple-barrier labeling functionality."""
    
    def setUp(self):
        """Set up test fixtures."""
        np.random.seed(42)
        # Generate synthetic price series (100 bars)
        returns = np.random.normal(0.001, 0.02, 100)
        self.prices = 100 * np.exp(np.cumsum(returns))
        
        self.labeler = TripleBarrierLabeler(
            take_profit=0.03,
            stop_loss=0.02,
            max_horizon=5
        )
    
    def test_initialization(self):
        """Test labeler initialization."""
        self.assertEqual(self.labeler.take_profit, 0.03)
        self.assertEqual(self.labeler.stop_loss, 0.02)
        self.assertEqual(self.labeler.max_horizon, 5)
    
    def test_invalid_parameters(self):
        """Test that invalid parameters raise errors."""
        with self.assertRaises(ValueError):
            TripleBarrierLabeler(take_profit=-0.01, stop_loss=0.02, max_horizon=5)
        
        with self.assertRaises(ValueError):
            TripleBarrierLabeler(take_profit=0.03, stop_loss=-0.02, max_horizon=5)
        
        with self.assertRaises(ValueError):
            TripleBarrierLabeler(take_profit=0.03, stop_loss=0.02, max_horizon=0)
    
    def test_apply_barriers_single_point(self):
        """Test barrier application at a single time point."""
        label, bars, ret = self.labeler.apply_barriers(self.prices, 50)
        
        # Check return types
        self.assertIsInstance(label, int)
        self.assertIsInstance(bars, int)
        self.assertIsInstance(ret, float)
        
        # Check label is valid
        self.assertIn(label, [-1, 0, 1])
        
        # Check bars is positive and within max_horizon
        self.assertGreater(bars, 0)
        self.assertLessEqual(bars, self.labeler.max_horizon)
    
    def test_apply_barriers_profit(self):
        """Test take-profit barrier."""
        # Create prices that will hit take-profit
        prices_up = np.array([100, 101, 102, 103, 104, 105])
        labeler = TripleBarrierLabeler(take_profit=0.02, stop_loss=0.1, max_horizon=5)
        
        label, bars, ret = labeler.apply_barriers(prices_up, 0)
        
        self.assertEqual(label, 1)  # Should hit profit
        self.assertGreater(ret, 0)  # Positive return
    
    def test_apply_barriers_loss(self):
        """Test stop-loss barrier."""
        # Create prices that will hit stop-loss
        prices_down = np.array([100, 99, 98, 97, 96, 95])
        labeler = TripleBarrierLabeler(take_profit=0.1, stop_loss=0.02, max_horizon=5)
        
        label, bars, ret = labeler.apply_barriers(prices_down, 0)
        
        self.assertEqual(label, -1)  # Should hit loss
        self.assertLess(ret, 0)  # Negative return
    
    def test_apply_barriers_timeout(self):
        """Test time horizon barrier (timeout)."""
        # Create prices that stay flat
        prices_flat = np.array([100, 100.5, 100.3, 100.2, 100.4, 100.1])
        labeler = TripleBarrierLabeler(take_profit=0.05, stop_loss=0.05, max_horizon=5)
        
        label, bars, ret = labeler.apply_barriers(prices_flat, 0)
        
        self.assertEqual(bars, 5)  # Should timeout at max_horizon
    
    def test_label_series(self):
        """Test labeling entire price series."""
        df = self.labeler.label_series(self.prices, min_observations=20)
        
        # Check DataFrame structure
        self.assertIsInstance(df, pd.DataFrame)
        self.assertIn('t_index', df.columns)
        self.assertIn('label', df.columns)
        self.assertIn('bars_to_exit', df.columns)
        self.assertIn('actual_return', df.columns)
        self.assertIn('entry_price', df.columns)
        
        # Check we have reasonable number of labels
        self.assertGreater(len(df), 0)
        self.assertLess(len(df), len(self.prices))
        
        # Check all labels are valid
        self.assertTrue(df['label'].isin([-1, 0, 1]).all())
        
        # Check bars_to_exit is within max_horizon
        self.assertTrue((df['bars_to_exit'] > 0).all())
        self.assertTrue((df['bars_to_exit'] <= self.labeler.max_horizon).all())
    
    def test_label_series_insufficient_data(self):
        """Test that insufficient data raises error."""
        short_prices = np.array([100, 101, 102])
        
        with self.assertRaises(ValueError):
            self.labeler.label_series(short_prices, min_observations=20)
    
    def test_label_distribution(self):
        """Test that label distribution is reasonable."""
        # Use larger price series
        returns = np.random.normal(0.001, 0.02, 1000)
        prices = 100 * np.exp(np.cumsum(returns))
        
        df = self.labeler.label_series(prices, min_observations=20)
        
        # Count labels
        profit_count = (df['label'] == 1).sum()
        loss_count = (df['label'] == -1).sum()
        neutral_count = (df['label'] == 0).sum()
        
        # Check that we have some of each label type
        # (with random walk, should have mixed labels)
        self.assertGreater(profit_count, 0)
        self.assertGreater(loss_count, 0)
        
        # Total should match
        self.assertEqual(profit_count + loss_count + neutral_count, len(df))


class TestMetaLabeler(unittest.TestCase):
    """Test meta-labeling functionality."""
    
    def setUp(self):
        """Set up test fixtures."""
        # Create mock barrier results
        self.barrier_results = pd.DataFrame({
            't_index': [0, 1, 2, 3, 4],
            'label': [1, -1, 0, 1, -1],
            'bars_to_exit': [3, 2, 5, 4, 1],
            'actual_return': [0.03, -0.02, 0.005, 0.04, -0.03],
            'entry_price': [100, 101, 102, 103, 104]
        })
        
        # Primary model predictions (some correct, some wrong)
        self.primary_labels = np.array([1, -1, 1, 1, 0])  # Mix of correct/incorrect
    
    def test_meta_labels_creation(self):
        """Test meta-label creation."""
        meta_labeler = MetaLabeler(self.primary_labels, self.barrier_results)
        meta_labels = meta_labeler.create_meta_labels()
        
        # Check output type and shape
        self.assertIsInstance(meta_labels, np.ndarray)
        self.assertEqual(len(meta_labels), len(self.primary_labels))
        
        # Check binary labels
        self.assertTrue(np.all(np.isin(meta_labels, [0, 1])))
    
    def test_meta_labels_correctness(self):
        """Test that meta-labels correctly identify correct predictions."""
        # Perfect primary predictions
        perfect_primary = np.array([1, -1, 0, 1, -1])
        
        meta_labeler = MetaLabeler(perfect_primary, self.barrier_results)
        meta_labels = meta_labeler.create_meta_labels()
        
        # All should be correct (label 1)
        self.assertTrue(np.all(meta_labels == 1))
    
    def test_meta_labels_all_wrong(self):
        """Test meta-labels when all predictions are wrong."""
        # All wrong primary predictions
        wrong_primary = np.array([-1, 1, 1, -1, 1])
        
        meta_labeler = MetaLabeler(wrong_primary, self.barrier_results)
        meta_labels = meta_labeler.create_meta_labels()
        
        # All should be wrong (label 0)
        self.assertTrue(np.all(meta_labels == 0))


class TestFractionalDifferentiation(unittest.TestCase):
    """Test fractional differentiation."""
    
    def test_fractional_diff_basic(self):
        """Test basic fractional differentiation."""
        series = np.arange(100, dtype=float)
        
        diff_series = fractional_differentiation(series, d=0.5)
        
        # Check output shape
        self.assertEqual(len(diff_series), len(series))
        
        # Check that beginning has NaN values
        self.assertTrue(np.isnan(diff_series[0]))
        
        # Check that later values are not NaN
        self.assertFalse(np.isnan(diff_series[-1]))
    
    def test_fractional_diff_invalid_d(self):
        """Test that invalid d parameter raises error."""
        series = np.arange(100, dtype=float)
        
        with self.assertRaises(ValueError):
            fractional_differentiation(series, d=0)
        
        with self.assertRaises(ValueError):
            fractional_differentiation(series, d=1.5)


class TestSampleWeights(unittest.TestCase):
    """Test sample weight generation."""
    
    def test_time_decay_weights(self):
        """Test time-decay weight generation."""
        weights = get_sample_weights_time_decay(100, decay_factor=0.95)
        
        # Check shape
        self.assertEqual(len(weights), 100)
        
        # Check that weights increase over time (recent samples heavier)
        self.assertLess(weights[0], weights[-1])
        
        # Check normalization (sum should equal number of samples)
        self.assertAlmostEqual(weights.sum(), 100, places=5)
    
    def test_time_decay_invalid_factor(self):
        """Test that invalid decay factor raises error."""
        with self.assertRaises(ValueError):
            get_sample_weights_time_decay(100, decay_factor=0)
        
        with self.assertRaises(ValueError):
            get_sample_weights_time_decay(100, decay_factor=1.5)
    
    def test_return_magnitude_weights(self):
        """Test return magnitude weight generation."""
        returns = np.array([0.01, -0.02, 0.03, -0.01, 0.00])
        
        weights = get_sample_weights_by_return(returns, absolute=True)
        
        # Check shape
        self.assertEqual(len(weights), len(returns))
        
        # Check that larger returns get higher weights
        # Index 2 has largest absolute return (0.03)
        max_weight_idx = np.argmax(weights)
        self.assertEqual(max_weight_idx, 2)
    
    def test_return_magnitude_weights_zero_returns(self):
        """Test handling of zero returns."""
        returns = np.zeros(10)
        
        weights = get_sample_weights_by_return(returns)
        
        # Should return uniform weights
        self.assertTrue(np.allclose(weights, 1.0))


if __name__ == "__main__":
    unittest.main()
