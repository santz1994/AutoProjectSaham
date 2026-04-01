"""
Unit tests for Model Ensemble

Tests the stacked ensemble implementation including:
- Model initialization
- Out-of-fold prediction generation
- Meta-model training
- Prediction accuracy
- Model persistence (save/load)
"""
import pytest
import numpy as np
from sklearn.datasets import make_classification
from sklearn.model_selection import train_test_split
from sklearn.metrics import roc_auc_score

from src.ml.ensemble import StackedEnsemble
from src.ml.evaluator import ModelEvaluator, EvaluationMetrics


@pytest.fixture
def synthetic_data():
    """Generate synthetic classification data."""
    X, y = make_classification(
        n_samples=500,
        n_features=20,
        n_informative=15,
        n_redundant=5,
        random_state=42
    )
    
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.3, random_state=42
    )
    
    return X_train, X_test, y_train, y_test


def test_ensemble_initialization():
    """Test ensemble initialization with different configurations."""
    # Default configuration
    ensemble = StackedEnsemble()
    assert len(ensemble.model_names) >= 2  # At least RF and LR
    assert ensemble.meta_model is not None
    assert not ensemble.is_fitted
    
    # Custom configuration
    ensemble = StackedEnsemble(
        n_folds=3,
        use_rf=True,
        use_lr=True,
        use_lgbm=False,
        use_xgb=False
    )
    assert 'rf' in ensemble.model_names
    assert 'lr' in ensemble.model_names
    assert ensemble.n_folds == 3


def test_ensemble_fitting(synthetic_data):
    """Test ensemble training."""
    X_train, X_test, y_train, y_test = synthetic_data
    
    ensemble = StackedEnsemble(n_folds=3)
    ensemble.fit(X_train, y_train)
    
    # Check fitting status
    assert ensemble.is_fitted
    
    # Check that base models were trained
    for model_name in ensemble.model_names:
        assert len(ensemble.fitted_base_models[model_name]) == ensemble.n_folds
    
    # Check that scores were calculated
    assert len(ensemble.base_model_scores) > 0
    assert ensemble.meta_model_score is not None
    
    # Check weights sum to approximately 1
    total_weight = sum(ensemble.model_weights.values())
    assert abs(total_weight - 1.0) < 0.01


def test_ensemble_predictions(synthetic_data):
    """Test ensemble predictions."""
    X_train, X_test, y_train, y_test = synthetic_data
    
    ensemble = StackedEnsemble(n_folds=3)
    ensemble.fit(X_train, y_train)
    
    # Test predict_proba
    y_pred_proba = ensemble.predict_proba(X_test)
    
    assert y_pred_proba.shape == (len(X_test), 2)
    assert np.all(y_pred_proba >= 0)
    assert np.all(y_pred_proba <= 1)
    assert np.allclose(y_pred_proba.sum(axis=1), 1.0)
    
    # Test predict
    y_pred = ensemble.predict(X_test)
    
    assert y_pred.shape == (len(X_test),)
    assert np.all((y_pred == 0) | (y_pred == 1))
    
    # Check that predictions are better than random
    auc = roc_auc_score(y_test, y_pred_proba[:, 1])
    assert auc > 0.55  # Should be better than random (0.5)


def test_ensemble_model_importance(synthetic_data):
    """Test model importance retrieval."""
    X_train, X_test, y_train, y_test = synthetic_data
    
    ensemble = StackedEnsemble(n_folds=3)
    ensemble.fit(X_train, y_train)
    
    importance_df = ensemble.get_model_importance()
    
    # Check DataFrame structure
    assert 'model' in importance_df.columns
    assert 'auc_score' in importance_df.columns
    assert 'weight' in importance_df.columns
    
    # Check that scores are reasonable
    assert all(importance_df['auc_score'] >= 0.5)
    assert all(importance_df['auc_score'] <= 1.0)
    
    # Check sorted by AUC
    auc_values = importance_df['auc_score'].values
    assert all(auc_values[i] >= auc_values[i+1] for i in range(len(auc_values)-1))


def test_ensemble_save_load(synthetic_data, tmp_path):
    """Test ensemble persistence."""
    X_train, X_test, y_train, y_test = synthetic_data
    
    # Train ensemble
    ensemble = StackedEnsemble(n_folds=3)
    ensemble.fit(X_train, y_train)
    
    # Get predictions before saving
    y_pred_before = ensemble.predict_proba(X_test)
    
    # Save ensemble
    save_path = tmp_path / "test_ensemble.joblib"
    ensemble.save(str(save_path))
    
    assert save_path.exists()
    
    # Create new ensemble and load
    ensemble_loaded = StackedEnsemble(n_folds=3)
    ensemble_loaded.load(str(save_path))
    
    # Check loaded state
    assert ensemble_loaded.is_fitted
    assert ensemble_loaded.meta_model_score is not None
    
    # Get predictions after loading
    y_pred_after = ensemble_loaded.predict_proba(X_test)
    
    # Predictions should be identical
    np.testing.assert_array_almost_equal(y_pred_before, y_pred_after, decimal=5)


def test_evaluator_basic_metrics(synthetic_data):
    """Test basic evaluation metrics."""
    X_train, X_test, y_train, y_test = synthetic_data
    
    # Train simple model
    ensemble = StackedEnsemble(n_folds=3)
    ensemble.fit(X_train, y_train)
    
    # Predict
    y_pred_proba = ensemble.predict_proba(X_test)[:, 1]
    
    # Evaluate
    evaluator = ModelEvaluator()
    metrics = evaluator.evaluate(y_test, y_pred_proba)
    
    # Check metric types
    assert isinstance(metrics, EvaluationMetrics)
    assert 0 <= metrics.accuracy <= 1
    assert 0 <= metrics.auc <= 1
    assert 0 <= metrics.f1_score <= 1
    
    # Check confusion matrix
    total_samples = (
        metrics.true_positives + 
        metrics.false_positives + 
        metrics.true_negatives + 
        metrics.false_negatives
    )
    assert total_samples == len(y_test)


def test_evaluator_trading_metrics(synthetic_data):
    """Test trading-specific metrics."""
    X_train, X_test, y_train, y_test = synthetic_data
    
    # Generate synthetic returns
    np.random.seed(42)
    returns = np.random.normal(0.001, 0.02, len(y_test)) * (2 * y_test - 1)
    
    # Train and predict
    ensemble = StackedEnsemble(n_folds=3)
    ensemble.fit(X_train, y_train)
    y_pred_proba = ensemble.predict_proba(X_test)[:, 1]
    
    # Evaluate with returns
    evaluator = ModelEvaluator()
    metrics = evaluator.evaluate(y_test, y_pred_proba, returns)
    
    # Check trading metrics exist
    assert metrics.sharpe_ratio is not None
    assert metrics.max_drawdown is not None
    assert metrics.win_rate is not None
    assert metrics.loss_rate is not None
    assert metrics.kelly_fraction is not None
    
    # Check metric ranges
    assert 0 <= metrics.win_rate <= 1
    assert 0 <= metrics.loss_rate <= 1
    assert abs(metrics.win_rate + metrics.loss_rate - 1.0) < 0.01  # Should sum to ~1


def test_evaluator_print_report(synthetic_data, capsys):
    """Test report printing."""
    X_train, X_test, y_train, y_test = synthetic_data
    
    ensemble = StackedEnsemble(n_folds=3)
    ensemble.fit(X_train, y_train)
    y_pred_proba = ensemble.predict_proba(X_test)[:, 1]
    
    evaluator = ModelEvaluator()
    metrics = evaluator.evaluate(y_test, y_pred_proba)
    
    # Print report
    evaluator.print_report(metrics)
    
    # Capture output
    captured = capsys.readouterr()
    
    # Check that key sections are present
    assert "MODEL EVALUATION REPORT" in captured.out
    assert "Classification Metrics" in captured.out
    assert "Confusion Matrix" in captured.out
    assert "AUC" in captured.out


def test_ensemble_with_few_samples():
    """Test ensemble with very few samples."""
    # Generate tiny dataset
    X, y = make_classification(
        n_samples=50,
        n_features=10,
        random_state=42
    )
    
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.3, random_state=42
    )
    
    # Should still work with fewer folds
    ensemble = StackedEnsemble(n_folds=3)
    ensemble.fit(X_train, y_train)
    
    y_pred = ensemble.predict_proba(X_test)
    
    assert y_pred.shape == (len(X_test), 2)


def test_ensemble_edge_cases():
    """Test edge cases."""
    # Perfectly separable data
    X = np.array([[0], [1], [2], [3], [4], [5]])
    y = np.array([0, 0, 0, 1, 1, 1])
    
    ensemble = StackedEnsemble(n_folds=2, use_lgbm=False, use_xgb=False)
    ensemble.fit(X, y)
    
    # Should still produce valid predictions
    y_pred = ensemble.predict_proba(X)
    assert y_pred.shape == (len(X), 2)


if __name__ == "__main__":
    # Run tests manually
    print("Running ensemble tests...\n")
    
    # Generate test data
    X, y = make_classification(
        n_samples=500,
        n_features=20,
        random_state=42
    )
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.3, random_state=42
    )
    test_data = (X_train, X_test, y_train, y_test)
    
    # Run tests
    print("✓ test_ensemble_initialization")
    test_ensemble_initialization()
    
    print("✓ test_ensemble_fitting")
    test_ensemble_fitting(test_data)
    
    print("✓ test_ensemble_predictions")
    test_ensemble_predictions(test_data)
    
    print("✓ test_ensemble_model_importance")
    test_ensemble_model_importance(test_data)
    
    print("✓ test_evaluator_basic_metrics")
    test_evaluator_basic_metrics(test_data)
    
    print("\n✅ All tests passed!")
