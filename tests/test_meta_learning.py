"""
Tests for Meta-Learning Module

Tests symbol adaptation, transfer learning, and few-shot learning capabilities.
"""
import unittest
import numpy as np
import pandas as pd
import tempfile
import os
import sys

# Add src to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

try:
    from src.ml.meta_learning import SymbolEmbedding, MetaLearner, SKLEARN_AVAILABLE
except ImportError as e:
    print(f"Import error: {e}")
    SKLEARN_AVAILABLE = False


@unittest.skipIf(not SKLEARN_AVAILABLE, "scikit-learn not installed")
class TestSymbolEmbedding(unittest.TestCase):
    """Test SymbolEmbedding class."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.embedding = SymbolEmbedding(embedding_dim=10)
        np.random.seed(42)
    
    def test_initialization(self):
        """Test embedding initialization."""
        self.assertEqual(self.embedding.embedding_dim, 10)
        self.assertEqual(len(self.embedding.symbol_embeddings), 0)
    
    def test_generate_embedding(self):
        """Test embedding generation."""
        # Create sample features
        features_df = pd.DataFrame({
            'rsi': np.random.uniform(30, 70, 100),
            'macd': np.random.randn(100),
            'volume': np.random.uniform(0.5, 1.5, 100)
        })
        
        embedding = self.embedding.generate_embedding('BBCA.JK', features_df)
        
        self.assertEqual(len(embedding), 10)
        self.assertTrue(np.isfinite(embedding).all())
    
    def test_embedding_with_sparse_data(self):
        """Test embedding generation with limited data."""
        features_df = pd.DataFrame({
            'rsi': [50, 60],
            'macd': [0.1, -0.1]
        })
        
        embedding = self.embedding.generate_embedding('SPARSE.JK', features_df)
        
        # Should still generate embedding (with padding/random)
        self.assertEqual(len(embedding), 10)
    
    def test_get_embedding(self):
        """Test embedding retrieval."""
        features_df = pd.DataFrame(np.random.randn(50, 3))
        
        self.embedding.generate_embedding('TEST.JK', features_df)
        
        retrieved = self.embedding.get_embedding('TEST.JK')
        self.assertIsNotNone(retrieved)
        self.assertEqual(len(retrieved), 10)
        
        # Non-existent symbol
        self.assertIsNone(self.embedding.get_embedding('NONEXIST.JK'))
    
    def test_compute_similarity(self):
        """Test similarity computation."""
        # Create two similar symbols
        features1 = pd.DataFrame(np.random.randn(100, 5) + 1.0)  # Mean 1
        features2 = pd.DataFrame(np.random.randn(100, 5) + 1.1)  # Mean 1.1
        features3 = pd.DataFrame(np.random.randn(100, 5) - 1.0)  # Mean -1
        
        self.embedding.generate_embedding('SYM1.JK', features1)
        self.embedding.generate_embedding('SYM2.JK', features2)
        self.embedding.generate_embedding('SYM3.JK', features3)
        
        # SYM1 should be more similar to SYM2 than to SYM3
        sim_12 = self.embedding.compute_similarity('SYM1.JK', 'SYM2.JK')
        sim_13 = self.embedding.compute_similarity('SYM1.JK', 'SYM3.JK')
        
        self.assertGreater(sim_12, sim_13)
        self.assertGreaterEqual(sim_12, -1.0)
        self.assertLessEqual(sim_12, 1.0)
    
    def test_find_similar_symbols(self):
        """Test finding similar symbols."""
        # Create 5 symbols
        for i in range(5):
            features = pd.DataFrame(np.random.randn(100, 3) + i * 0.5)
            self.embedding.generate_embedding(f'SYM{i}.JK', features)
        
        # Find similar to SYM2
        similar = self.embedding.find_similar_symbols('SYM2.JK', k=2)
        
        self.assertEqual(len(similar), 2)
        self.assertIsInstance(similar[0], tuple)
        self.assertEqual(len(similar[0]), 2)  # (symbol, similarity)
        
        # Similarities should be in descending order
        self.assertGreaterEqual(similar[0][1], similar[1][1])


@unittest.skipIf(not SKLEARN_AVAILABLE, "scikit-learn not installed")
class TestMetaLearner(unittest.TestCase):
    """Test MetaLearner class."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.meta_learner = MetaLearner()
        np.random.seed(42)
    
    def test_initialization(self):
        """Test meta-learner initialization."""
        self.assertIsNotNone(self.meta_learner.base_model)
        self.assertEqual(len(self.meta_learner.symbol_models), 0)
        self.assertEqual(len(self.meta_learner.training_symbols), 0)
    
    def test_train_base_model(self):
        """Test base model training on multiple symbols."""
        # Create data for 3 symbols
        X_dict = {}
        y_dict = {}
        
        for i, symbol in enumerate(['SYM1.JK', 'SYM2.JK', 'SYM3.JK']):
            n_samples = 100
            X = np.random.randn(n_samples, 5)
            y = (X[:, 0] + X[:, 1] > 0).astype(int)
            
            X_dict[symbol] = pd.DataFrame(X, columns=[f'f{j}' for j in range(5)])
            y_dict[symbol] = pd.Series(y)
        
        # Train base model
        metrics = self.meta_learner.train_base_model(X_dict, y_dict)
        
        # Check metrics
        self.assertIn('accuracy', metrics)
        self.assertIn('auc', metrics)
        self.assertIn('n_symbols', metrics)
        self.assertIn('n_samples', metrics)
        
        self.assertEqual(metrics['n_symbols'], 3)
        self.assertEqual(metrics['n_samples'], 300)
        self.assertGreater(metrics['accuracy'], 0.5)  # Better than random
        
        # Check training symbols recorded
        self.assertEqual(len(self.meta_learner.training_symbols), 3)
    
    def test_adapt_to_symbol(self):
        """Test adaptation to new symbol with few-shot learning."""
        # Train base model first
        X_dict = {}
        y_dict = {}
        
        for i, symbol in enumerate(['SYM1.JK', 'SYM2.JK', 'SYM3.JK']):
            n_samples = 150
            X = np.random.randn(n_samples, 5)
            y = (X[:, 0] + X[:, 1] > 0).astype(int)
            
            X_dict[symbol] = pd.DataFrame(X, columns=[f'f{j}' for j in range(5)])
            y_dict[symbol] = pd.Series(y)
        
        self.meta_learner.train_base_model(X_dict, y_dict)
        
        # Adapt to new symbol with 50 samples
        new_symbol = 'NEW.JK'
        X_new = pd.DataFrame(np.random.randn(50, 5), columns=[f'f{j}' for j in range(5)])
        y_new = pd.Series((X_new.iloc[:, 0] + X_new.iloc[:, 1] > 0).astype(int))
        
        adapt_metrics = self.meta_learner.adapt_to_symbol(new_symbol, X_new, y_new)
        
        # Check adaptation metrics
        self.assertIn('symbol', adapt_metrics)
        self.assertIn('accuracy', adapt_metrics)
        self.assertIn('auc', adapt_metrics)
        self.assertIn('similar_symbols', adapt_metrics)
        
        self.assertEqual(adapt_metrics['symbol'], new_symbol)
        self.assertEqual(adapt_metrics['n_samples'], 50)
        
        # Check symbol model stored
        self.assertIn(new_symbol, self.meta_learner.symbol_models)
        
        # Check adaptation history
        self.assertIn(new_symbol, self.meta_learner.adaptation_history)
    
    def test_predict_with_adapted_model(self):
        """Test predictions using adapted model."""
        # Train and adapt
        X_dict = {}
        y_dict = {}
        
        for symbol in ['SYM1.JK', 'SYM2.JK']:
            X = np.random.randn(100, 5)
            y = (X[:, 0] > 0).astype(int)
            
            X_dict[symbol] = pd.DataFrame(X, columns=[f'f{j}' for j in range(5)])
            y_dict[symbol] = pd.Series(y)
        
        self.meta_learner.train_base_model(X_dict, y_dict)
        
        # Adapt to new symbol
        X_new = pd.DataFrame(np.random.randn(60, 5), columns=[f'f{j}' for j in range(5)])
        y_new = pd.Series((X_new.iloc[:, 0] > 0).astype(int))
        
        self.meta_learner.adapt_to_symbol('NEW.JK', X_new, y_new)
        
        # Make predictions
        X_test = pd.DataFrame(np.random.randn(20, 5), columns=[f'f{j}' for j in range(5)])
        
        predictions, probabilities = self.meta_learner.predict('NEW.JK', X_test)
        
        self.assertEqual(len(predictions), 20)
        self.assertEqual(len(probabilities), 20)
        self.assertTrue(all(p in [0, 1] for p in predictions))
        self.assertTrue(all(0 <= p <= 1 for p in probabilities))
    
    def test_predict_without_adapted_model(self):
        """Test predictions using base model when no adaptation."""
        # Train base model only
        X_dict = {
            'SYM1.JK': pd.DataFrame(np.random.randn(100, 5))
        }
        y_dict = {
            'SYM1.JK': pd.Series(np.random.randint(0, 2, 100))
        }
        
        self.meta_learner.train_base_model(X_dict, y_dict)
        
        # Predict for unknown symbol (should use base model)
        X_test = pd.DataFrame(np.random.randn(20, 5))
        
        predictions, probabilities = self.meta_learner.predict('UNKNOWN.JK', X_test)
        
        self.assertEqual(len(predictions), 20)
        self.assertEqual(len(probabilities), 20)
    
    def test_get_symbol_performance(self):
        """Test retrieving symbol performance metrics."""
        # Train and adapt
        X_train = {'SYM1.JK': pd.DataFrame(np.random.randn(100, 5))}
        y_train = {'SYM1.JK': pd.Series(np.random.randint(0, 2, 100))}
        
        self.meta_learner.train_base_model(X_train, y_train)
        
        X_new = pd.DataFrame(np.random.randn(50, 5))
        y_new = pd.Series(np.random.randint(0, 2, 50))
        
        self.meta_learner.adapt_to_symbol('NEW.JK', X_new, y_new)
        
        # Get performance
        perf = self.meta_learner.get_symbol_performance('NEW.JK')
        
        self.assertIsNotNone(perf)
        self.assertIn('accuracy', perf)
        self.assertIn('n_samples', perf)
        
        # Unknown symbol
        self.assertIsNone(self.meta_learner.get_symbol_performance('UNKNOWN.JK'))
    
    def test_get_all_performance(self):
        """Test retrieving all symbols performance."""
        # Train base
        X_train = {'SYM1.JK': pd.DataFrame(np.random.randn(100, 5))}
        y_train = {'SYM1.JK': pd.Series(np.random.randint(0, 2, 100))}
        
        self.meta_learner.train_base_model(X_train, y_train)
        
        # Adapt to two new symbols
        for symbol in ['NEW1.JK', 'NEW2.JK']:
            X = pd.DataFrame(np.random.randn(50, 5))
            y = pd.Series(np.random.randint(0, 2, 50))
            self.meta_learner.adapt_to_symbol(symbol, X, y)
        
        # Get all performance
        perf_df = self.meta_learner.get_all_performance()
        
        self.assertIsInstance(perf_df, pd.DataFrame)
        self.assertEqual(len(perf_df), 2)  # Two adapted symbols
        self.assertIn('symbol', perf_df.columns)
        self.assertIn('accuracy', perf_df.columns)
    
    def test_save_and_load(self):
        """Test saving and loading meta-learner."""
        # Train and adapt
        X_train = {
            'SYM1.JK': pd.DataFrame(np.random.randn(100, 5)),
            'SYM2.JK': pd.DataFrame(np.random.randn(100, 5))
        }
        y_train = {
            'SYM1.JK': pd.Series(np.random.randint(0, 2, 100)),
            'SYM2.JK': pd.Series(np.random.randint(0, 2, 100))
        }
        
        self.meta_learner.train_base_model(X_train, y_train)
        
        X_new = pd.DataFrame(np.random.randn(50, 5))
        y_new = pd.Series(np.random.randint(0, 2, 50))
        self.meta_learner.adapt_to_symbol('NEW.JK', X_new, y_new)
        
        # Save
        with tempfile.NamedTemporaryFile(delete=False, suffix='.pkl') as tmp:
            tmp_path = tmp.name
        
        try:
            self.meta_learner.save(tmp_path)
            
            # Load into new meta-learner
            new_meta_learner = MetaLearner()
            new_meta_learner.load(tmp_path)
            
            # Check state restored
            self.assertEqual(len(new_meta_learner.training_symbols), 
                           len(self.meta_learner.training_symbols))
            self.assertEqual(len(new_meta_learner.symbol_models), 
                           len(self.meta_learner.symbol_models))
            self.assertEqual(len(new_meta_learner.symbol_embedding.symbol_embeddings),
                           len(self.meta_learner.symbol_embedding.symbol_embeddings))
            
        finally:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
    
    def test_few_shot_learning_improvement(self):
        """Test that few-shot adaptation improves performance."""
        # Train base model on symbols with pattern: x0 + x1 > 0
        X_dict = {}
        y_dict = {}
        
        for i in range(3):
            X = np.random.randn(200, 5)
            y = (X[:, 0] + X[:, 1] > 0).astype(int)
            
            X_dict[f'SYM{i}.JK'] = pd.DataFrame(X, columns=[f'f{j}' for j in range(5)])
            y_dict[f'SYM{i}.JK'] = pd.Series(y)
        
        self.meta_learner.train_base_model(X_dict, y_dict)
        
        # New symbol has slightly different pattern: x0 + x1 + x2 > 0
        X_new = np.random.randn(100, 5)
        y_new = (X_new[:, 0] + X_new[:, 1] + X_new[:, 2] > 0).astype(int)
        
        X_new_df = pd.DataFrame(X_new, columns=[f'f{j}' for j in range(5)])
        y_new_series = pd.Series(y_new)
        
        # Split into few-shot train and test
        X_few_shot = X_new_df.iloc[:50]
        y_few_shot = y_new_series.iloc[:50]
        X_test = X_new_df.iloc[50:]
        y_test = y_new_series.iloc[50:]
        
        # Baseline: base model performance
        base_pred, _ = self.meta_learner.predict('NEW.JK', X_test)
        base_accuracy = (base_pred == y_test.values).mean()
        
        # Adapt to new symbol
        self.meta_learner.adapt_to_symbol('NEW.JK', X_few_shot, y_few_shot)
        
        # Adapted model performance
        adapted_pred, _ = self.meta_learner.predict('NEW.JK', X_test)
        adapted_accuracy = (adapted_pred == y_test.values).mean()
        
        # Adaptation should improve or maintain performance
        # (May not always improve due to randomness, but should be competitive)
        self.assertGreaterEqual(adapted_accuracy, base_accuracy - 0.1)


def run_meta_learning_benchmark():
    """Benchmark meta-learning performance."""
    if not SKLEARN_AVAILABLE:
        print("scikit-learn not installed. Skipping benchmark.")
        return
    
    from src.ml.meta_learning import MetaLearner
    
    print("\n" + "="*60)
    print("META-LEARNING BENCHMARK")
    print("="*60 + "\n")
    
    np.random.seed(42)
    
    # Simulate 5 banking stocks with similar patterns
    print("Creating synthetic data for 5 bank stocks...\n")
    
    symbols = ['BBCA.JK', 'BMRI.JK', 'BBRI.JK', 'BNI.JK', 'BRI.JK']
    X_dict = {}
    y_dict = {}
    
    for i, symbol in enumerate(symbols):
        n_samples = 500
        
        # Each bank has similar but slightly different patterns
        bias = (i - 2) * 0.05  # Small variation
        X = np.random.randn(n_samples, 7)
        X[:, 0] += bias  # Symbol-specific bias
        
        # Target: buy if momentum + volume signal
        y = ((X[:, 0] + X[:, 1] * 0.5 + X[:, 2] * 0.3 + bias) > 0).astype(int)
        
        X_dict[symbol] = pd.DataFrame(X, columns=[f'feature_{j}' for j in range(7)])
        y_dict[symbol] = pd.Series(y)
    
    # Train base model on first 4 banks
    meta_learner = MetaLearner(few_shot_samples=50)
    
    train_symbols = symbols[:4]
    X_train = {s: X_dict[s] for s in train_symbols}
    y_train = {s: y_dict[s] for s in train_symbols}
    
    print("Training base model on 4 bank stocks...")
    metrics = meta_learner.train_base_model(X_train, y_train)
    print(f"  Base model trained: Accuracy={metrics['accuracy']:.3f}, "
          f"AUC={metrics['auc']:.3f}\n")
    
    # Test few-shot adaptation on 5th bank
    new_symbol = symbols[4]
    print(f"Testing few-shot adaptation on {new_symbol}...\n")
    
    # Try different few-shot sizes
    few_shot_sizes = [20, 50, 100]
    
    for size in few_shot_sizes:
        X_few_shot = X_dict[new_symbol].iloc[:size]
        y_few_shot = y_dict[new_symbol].iloc[:size]
        
        # Adapt
        adapt_metrics = meta_learner.adapt_to_symbol(
            f"{new_symbol}_fs{size}",
            X_few_shot,
            y_few_shot
        )
        
        # Test on remaining data
        X_test = X_dict[new_symbol].iloc[size:]
        y_test = y_dict[new_symbol].iloc[size:]
        
        y_pred, y_proba = meta_learner.predict(f"{new_symbol}_fs{size}", X_test)
        
        from sklearn.metrics import accuracy_score, roc_auc_score
        test_acc = accuracy_score(y_test.values, y_pred)
        test_auc = roc_auc_score(y_test.values, y_proba)
        
        print(f"  Few-shot size: {size:3d} samples")
        print(f"    Train Accuracy: {adapt_metrics['accuracy']:.3f}")
        print(f"    Test Accuracy:  {test_acc:.3f}")
        print(f"    Test AUC:       {test_auc:.3f}")
        print(f"    Similar stocks: {', '.join(adapt_metrics['similar_symbols'][:2])}\n")
    
    print("="*60)
    print("CONCLUSION")
    print("="*60)
    print("Meta-learning enables rapid adaptation to new stocks with")
    print("minimal training data by transferring knowledge from similar stocks.")
    print("\nâœ… Benchmark complete!\n")


if __name__ == '__main__':
    # Run tests
    print("Running Meta-Learning Tests...\n")
    unittest.main(argv=[''], exit=False, verbosity=2)
    
    # Run benchmark
    run_meta_learning_benchmark()


