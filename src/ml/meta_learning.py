"""
Meta-Learning for Symbol Adaptation

Enables rapid adaptation to new stock symbols with minimal training data.
Uses transfer learning and few-shot learning techniques to:
1. Learn a global "base" model across multiple symbols
2. Quickly adapt to new symbols with <100 samples
3. Transfer knowledge between related symbols
4. Generate symbol embeddings for similarity analysis

This is crucial for IDX where some stocks have limited historical data.
"""
from __future__ import annotations

from typing import Dict, List, Optional, Tuple, Any
from collections import defaultdict
import numpy as np
import pandas as pd
from datetime import datetime
from pathlib import Path
import joblib
import logging

try:
    from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import accuracy_score, roc_auc_score
    SKLEARN_AVAILABLE = True
except ImportError:
    SKLEARN_AVAILABLE = False

logger = logging.getLogger(__name__)


class SymbolEmbedding:
    """
    Generate embeddings for stock symbols based on their features.
    
    Embeddings capture trading characteristics:
    - Volatility profile
    - Liquidity patterns
    - Price momentum characteristics
    - Correlation with market indices
    """
    
    def __init__(self, embedding_dim: int = 10):
        """
        Initialize symbol embedding generator.
        
        Args:
            embedding_dim: Dimension of embedding vectors
        """
        self.embedding_dim = embedding_dim
        self.symbol_embeddings: Dict[str, np.ndarray] = {}
    
    def generate_embedding(
        self,
        symbol: str,
        features_df: pd.DataFrame
    ) -> np.ndarray:
        """
        Generate embedding for a symbol from its features.
        
        Args:
            symbol: Stock symbol (e.g., 'BBCA.JK')
            features_df: DataFrame with features for this symbol
            
        Returns:
            Embedding vector (embedding_dim,)
        """
        if len(features_df) < 10:
            # Not enough data, use random embedding
            embedding = np.random.randn(self.embedding_dim) * 0.1
        else:
            # Compute statistical features
            numerical_cols = features_df.select_dtypes(include=[np.number]).columns
            
            stats = []
            for col in numerical_cols:
                if col in features_df:
                    values = features_df[col].dropna()
                    if len(values) > 0:
                        stats.extend([
                            values.mean(),
                            values.std(),
                            values.quantile(0.25),
                            values.quantile(0.75)
                        ])
            
            # Truncate or pad to embedding_dim
            stats_array = np.array(stats)
            if len(stats_array) >= self.embedding_dim:
                embedding = stats_array[:self.embedding_dim]
            else:
                embedding = np.pad(stats_array, (0, self.embedding_dim - len(stats_array)))

            # Normalize within the embedding vector to keep relative structure
            # while avoiding the single-row StandardScaler all-zero pitfall.
            mean = float(np.mean(embedding))
            std = float(np.std(embedding))
            if std > 1e-12:
                embedding = (embedding - mean) / std
            else:
                embedding = embedding - mean
        
        self.symbol_embeddings[symbol] = embedding
        return embedding
    
    def get_embedding(self, symbol: str) -> Optional[np.ndarray]:
        """
        Get cached embedding for a symbol.
        
        Args:
            symbol: Stock symbol
            
        Returns:
            Embedding vector or None if not computed
        """
        return self.symbol_embeddings.get(symbol)
    
    def compute_similarity(self, symbol1: str, symbol2: str) -> float:
        """
        Compute cosine similarity between two symbols.
        
        Args:
            symbol1: First symbol
            symbol2: Second symbol
            
        Returns:
            Similarity score (0 to 1)
        """
        emb1 = self.get_embedding(symbol1)
        emb2 = self.get_embedding(symbol2)
        
        if emb1 is None or emb2 is None:
            return 0.0
        
        # Cosine similarity
        dot_product = np.dot(emb1, emb2)
        norm1 = np.linalg.norm(emb1)
        norm2 = np.linalg.norm(emb2)
        
        if norm1 == 0 or norm2 == 0:
            return 0.0
        
        return float(dot_product / (norm1 * norm2))
    
    def find_similar_symbols(
        self,
        target_symbol: str,
        k: int = 5
    ) -> List[Tuple[str, float]]:
        """
        Find k most similar symbols to target.
        
        Args:
            target_symbol: Symbol to find similar symbols for
            k: Number of similar symbols to return
            
        Returns:
            List of (symbol, similarity) tuples
        """
        target_emb = self.get_embedding(target_symbol)
        if target_emb is None:
            return []
        
        similarities = []
        for symbol, emb in self.symbol_embeddings.items():
            if symbol != target_symbol:
                sim = self.compute_similarity(target_symbol, symbol)
                similarities.append((symbol, sim))
        
        # Sort by similarity (descending)
        similarities.sort(key=lambda x: x[1], reverse=True)
        
        return similarities[:k]


class MetaLearner:
    """
    Meta-learning system for fast adaptation to new symbols.
    
    Architecture:
    1. Global base model trained on all symbols
    2. Symbol-specific adaptation layers
    3. Transfer learning from similar symbols
    4. Few-shot fine-tuning for new symbols
    """
    
    def __init__(
        self,
        base_model: Optional[Any] = None,
        adaptation_lr: float = 0.01,
        few_shot_samples: int = 50
    ):
        """
        Initialize meta-learner.
        
        Args:
            base_model: Pre-trained base model (sklearn-compatible)
            adaptation_lr: Learning rate for adaptation
            few_shot_samples: Minimum samples for few-shot learning
        """
        if not SKLEARN_AVAILABLE:
            raise ImportError("scikit-learn required for meta-learning")
        
        # Global base model (trained on all symbols)
        self.base_model = base_model or GradientBoostingClassifier(
            n_estimators=100,
            max_depth=3,
            learning_rate=0.1,
            random_state=42
        )
        
        # Symbol-specific models
        self.symbol_models: Dict[str, Any] = {}
        self.symbol_model_uses_base_proba: Dict[str, bool] = {}
        
        # Symbol embeddings
        self.symbol_embedding = SymbolEmbedding(embedding_dim=10)
        
        # Configuration
        self.adaptation_lr = adaptation_lr
        self.few_shot_samples = few_shot_samples
        
        # Training history
        self.training_symbols: List[str] = []
        self.adaptation_history: Dict[str, List[Dict]] = defaultdict(list)
    
    def train_base_model(
        self,
        X_dict: Dict[str, pd.DataFrame],
        y_dict: Dict[str, pd.Series]
    ) -> Dict[str, float]:
        """
        Train global base model on multiple symbols.
        
        Args:
            X_dict: Dictionary {symbol: features_df}
            y_dict: Dictionary {symbol: labels_series}
            
        Returns:
            Dictionary with training metrics
        """
        # Combine all data
        X_all = []
        y_all = []
        
        for symbol in X_dict.keys():
            if symbol in y_dict:
                X_all.append(X_dict[symbol].values)
                y_all.append(y_dict[symbol].values)
                
                # Generate symbol embedding
                self.symbol_embedding.generate_embedding(symbol, X_dict[symbol])
                
                if symbol not in self.training_symbols:
                    self.training_symbols.append(symbol)
        
        if not X_all:
            raise ValueError("No training data provided")
        
        X_combined = np.vstack(X_all)
        y_combined = np.concatenate(y_all)
        
        # Train base model
        logger.info(f"Training base model on {len(self.training_symbols)} symbols "
                   f"({len(y_combined)} total samples)")
        
        self.base_model.fit(X_combined, y_combined)
        
        # Evaluate on training data
        y_pred = self.base_model.predict(X_combined)
        accuracy = accuracy_score(y_combined, y_pred)
        
        try:
            y_pred_proba = self.base_model.predict_proba(X_combined)[:, 1]
            auc = roc_auc_score(y_combined, y_pred_proba)
        except:
            auc = accuracy
        
        logger.info(f"Base model trained: Accuracy={accuracy:.3f}, AUC={auc:.3f}")
        
        return {
            'accuracy': float(accuracy),
            'auc': float(auc),
            'n_symbols': len(self.training_symbols),
            'n_samples': len(y_combined)
        }
    
    def adapt_to_symbol(
        self,
        symbol: str,
        X_few_shot: pd.DataFrame,
        y_few_shot: pd.Series,
        similar_symbols: Optional[List[str]] = None
    ) -> Dict[str, float]:
        """
        Rapidly adapt to a new symbol with few-shot learning.
        
        Args:
            symbol: New symbol to adapt to
            X_few_shot: Few-shot training features (50-100 samples)
            y_few_shot: Few-shot training labels
            similar_symbols: Known similar symbols (optional)
            
        Returns:
            Dictionary with adaptation metrics
        """
        if len(X_few_shot) < 10:
            logger.warning(f"Very few samples ({len(X_few_shot)}) for {symbol}")
        
        # Generate embedding for new symbol
        self.symbol_embedding.generate_embedding(symbol, X_few_shot)
        
        # Find similar symbols if not provided
        if similar_symbols is None:
            similar_pairs = self.symbol_embedding.find_similar_symbols(symbol, k=3)
            similar_symbols = [s for s, _ in similar_pairs]
        
        logger.info(f"Adapting to {symbol} using similar symbols: {similar_symbols}")
        
        # Strategy 1: Fine-tune base model
        uses_base_proba = False
        if len(X_few_shot) >= self.few_shot_samples:
            # Sufficient data for fine-tuning
            adapted_model = GradientBoostingClassifier(
                n_estimators=50,
                max_depth=3,
                learning_rate=self.adaptation_lr,
                random_state=42
            )
            
            # Initialize with base model predictions as features (stacking)
            X_aug = X_few_shot.copy()
            if hasattr(self.base_model, 'predict_proba'):
                base_proba = self.base_model.predict_proba(X_few_shot.values)[:, 1]
                X_aug['base_model_proba'] = base_proba
                uses_base_proba = True
            
            adapted_model.fit(X_aug.values, y_few_shot.values)
            
        else:
            # Too few samples, use weighted base model
            adapted_model = self.base_model
            X_aug = X_few_shot

        X_eval = X_aug.values if uses_base_proba else X_few_shot.values
        
        # Evaluate adaptation
        y_pred = adapted_model.predict(X_eval)
        accuracy = accuracy_score(y_few_shot.values, y_pred)
        
        try:
            y_pred_proba = adapted_model.predict_proba(X_eval)[:, 1]
            auc = roc_auc_score(y_few_shot.values, y_pred_proba)
        except:
            auc = accuracy
        
        # Store adapted model
        self.symbol_models[symbol] = adapted_model
        self.symbol_model_uses_base_proba[symbol] = uses_base_proba
        
        # Record adaptation
        self.adaptation_history[symbol].append({
            'timestamp': datetime.now().isoformat(),
            'n_samples': len(X_few_shot),
            'accuracy': float(accuracy),
            'auc': float(auc),
            'similar_symbols': similar_symbols
        })
        
        logger.info(f"Adapted to {symbol}: Accuracy={accuracy:.3f}, AUC={auc:.3f}")
        
        return {
            'symbol': symbol,
            'accuracy': float(accuracy),
            'auc': float(auc),
            'n_samples': len(X_few_shot),
            'similar_symbols': similar_symbols
        }
    
    def predict(
        self,
        symbol: str,
        X: pd.DataFrame
    ) -> Tuple[np.ndarray, np.ndarray]:
        """
        Make predictions for a symbol.
        
        Args:
            symbol: Stock symbol
            X: Feature DataFrame
            
        Returns:
            Tuple of (predictions, probabilities)
        """
        # Use symbol-specific model if available
        if symbol in self.symbol_models:
            model = self.symbol_models[symbol]
            uses_base_proba = self.symbol_model_uses_base_proba.get(symbol, False)
        else:
            # Fall back to base model
            model = self.base_model
            uses_base_proba = False
            logger.debug(f"No adapted model for {symbol}, using base model")

        if uses_base_proba and hasattr(self.base_model, 'predict_proba'):
            X_infer = X.copy()
            X_infer['base_model_proba'] = self.base_model.predict_proba(X.values)[:, 1]
            infer_values = X_infer.values
        else:
            infer_values = X.values

        predictions = model.predict(infer_values)
        
        if hasattr(model, 'predict_proba'):
            probabilities = model.predict_proba(infer_values)[:, 1]
        else:
            probabilities = predictions.astype(float)
        
        return predictions, probabilities
    
    def get_symbol_performance(self, symbol: str) -> Optional[Dict]:
        """
        Get performance metrics for a symbol.
        
        Args:
            symbol: Stock symbol
            
        Returns:
            Latest performance metrics or None
        """
        if symbol not in self.adaptation_history:
            return None
        
        return self.adaptation_history[symbol][-1] if self.adaptation_history[symbol] else None
    
    def get_all_performance(self) -> pd.DataFrame:
        """
        Get performance metrics for all adapted symbols.
        
        Returns:
            DataFrame with performance metrics
        """
        records = []
        for symbol, history in self.adaptation_history.items():
            if history:
                latest = history[-1]
                records.append({
                    'symbol': symbol,
                    'accuracy': latest['accuracy'],
                    'auc': latest['auc'],
                    'n_samples': latest['n_samples'],
                    'n_adaptations': len(history),
                    'similar_symbols': ', '.join(latest.get('similar_symbols', []))
                })
        
        return pd.DataFrame(records) if records else pd.DataFrame()
    
    def save(self, filepath: str) -> None:
        """
        Save meta-learner state.
        
        Args:
            filepath: Path to save file
        """
        Path(filepath).parent.mkdir(parents=True, exist_ok=True)
        
        state = {
            'base_model': self.base_model,
            'symbol_models': self.symbol_models,
            'symbol_model_uses_base_proba': self.symbol_model_uses_base_proba,
            'symbol_embeddings': self.symbol_embedding.symbol_embeddings,
            'training_symbols': self.training_symbols,
            'adaptation_history': dict(self.adaptation_history)
        }
        
        joblib.dump(state, filepath)
        logger.info(f"Meta-learner saved to {filepath}")
    
    def load(self, filepath: str) -> None:
        """
        Load meta-learner state.
        
        Args:
            filepath: Path to load file
        """
        state = joblib.load(filepath)
        
        self.base_model = state['base_model']
        self.symbol_models = state['symbol_models']
        self.symbol_model_uses_base_proba = state.get('symbol_model_uses_base_proba', {})
        self.symbol_embedding.symbol_embeddings = state['symbol_embeddings']
        self.training_symbols = state['training_symbols']
        self.adaptation_history = defaultdict(list, state['adaptation_history'])
        
        logger.info(f"Meta-learner loaded from {filepath}")


if __name__ == "__main__":
    # Demo meta-learning
    print("=== Meta-Learning for Symbol Adaptation Demo ===\n")
    
    if not SKLEARN_AVAILABLE:
        print("ERROR: scikit-learn not installed")
        exit(1)
    
    np.random.seed(42)
    
    # Simulate data for 5 symbols
    print("Generating synthetic data for 5 symbols...\n")
    
    symbols = ['BBCA.JK', 'BMRI.JK', 'BBRI.JK', 'TLKM.JK', 'ASII.JK']
    X_dict = {}
    y_dict = {}
    
    for i, symbol in enumerate(symbols):
        n_samples = 500
        
        # Each symbol has slightly different patterns
        bias = (i - 2) * 0.1
        X = np.random.randn(n_samples, 5)
        X[:, 0] += bias  # Symbol-specific bias
        
        # Target: positive if weighted sum > threshold
        y = ((X[:, 0] + X[:, 1] + bias) > 0).astype(int)
        
        X_dict[symbol] = pd.DataFrame(X, columns=[f'f{j}' for j in range(5)])
        y_dict[symbol] = pd.Series(y)
    
    # Create meta-learner
    meta_learner = MetaLearner()
    
    # Train base model on first 4 symbols
    train_symbols = symbols[:4]
    X_train = {s: X_dict[s] for s in train_symbols}
    y_train = {s: y_dict[s] for s in train_symbols}
    
    print("Training base model on 4 symbols...")
    metrics = meta_learner.train_base_model(X_train, y_train)
    print(f"  Base model: Accuracy={metrics['accuracy']:.3f}, AUC={metrics['auc']:.3f}\n")
    
    # Adapt to new symbol with few-shot learning
    new_symbol = symbols[4]
    print(f"Adapting to new symbol {new_symbol} with 50 samples (few-shot)...")
    
    X_few_shot = X_dict[new_symbol].iloc[:50]
    y_few_shot = y_dict[new_symbol].iloc[:50]
    
    adapt_metrics = meta_learner.adapt_to_symbol(new_symbol, X_few_shot, y_few_shot)
    print(f"  Adapted model: Accuracy={adapt_metrics['accuracy']:.3f}, "
          f"AUC={adapt_metrics['auc']:.3f}")
    print(f"  Similar symbols: {adapt_metrics['similar_symbols']}\n")
    
    # Evaluate on test set
    X_test = X_dict[new_symbol].iloc[50:]
    y_test = y_dict[new_symbol].iloc[50:]
    
    y_pred, y_proba = meta_learner.predict(new_symbol, X_test)
    test_accuracy = accuracy_score(y_test.values, y_pred)
    test_auc = roc_auc_score(y_test.values, y_proba)
    
    print(f"Test Performance on {new_symbol}:")
    print(f"  Accuracy: {test_accuracy:.3f}")
    print(f"  AUC: {test_auc:.3f}\n")
    
    # Show all performance
    print("All Symbol Performance:")
    print(meta_learner.get_all_performance().to_string(index=False))
    
    # Save meta-learner
    save_path = "models/meta_learner_demo.pkl"
    meta_learner.save(save_path)
    print(f"\n✅ Meta-learner saved to {save_path}")
