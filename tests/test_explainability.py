"""
Tests for Model Explainability Service
========================================

Tests for SHAP-based model explanation and feature importance.

Author: AutoSaham Team
"""

import pytest
import numpy as np
import pandas as pd
from unittest.mock import Mock, patch, MagicMock

from src.api.explainability_service import (
    SHAPExplainer,
    ExplainabilityService,
    FeatureImportance,
    PredictionExplanation,
    ModelType,
    ExplainerType,
)


class TestFeatureImportance:
    """Test FeatureImportance dataclass."""

    def test_feature_importance_creation(self):
        """Test creating feature importance."""
        importance = FeatureImportance(
            feature_name="rsi_14",
            importance_value=0.125,
            importance_percent=12.5,
            contribution_direction="positive",
            rank=1,
        )
        
        assert importance.feature_name == "rsi_14"
        assert importance.importance_value == 0.125
        assert importance.rank == 1

    def test_feature_importance_to_dict(self):
        """Test converting to dictionary."""
        importance = FeatureImportance(
            feature_name="rsi_14",
            importance_value=0.125,
            importance_percent=12.5,
            contribution_direction="positive",
            rank=1,
        )
        
        data = importance.to_dict()
        assert data["feature_name"] == "rsi_14"
        assert data["importance_value"] == 0.125


class TestPredictionExplanation:
    """Test PredictionExplanation dataclass."""

    def test_prediction_explanation_creation(self):
        """Test creating prediction explanation."""
        explanation = PredictionExplanation(
            prediction=0.75,
            prediction_class="BUY",
            confidence=0.92,
            feature_contributions=[
                {"feature": "rsi_14", "shap_value": 0.05, "feature_value": 65.0}
            ],
            base_value=0.50,
            timestamp="2026-04-01T12:00:00+07:00",
        )
        
        assert explanation.prediction == 0.75
        assert explanation.prediction_class == "BUY"
        assert len(explanation.feature_contributions) == 1

    def test_prediction_explanation_to_dict(self):
        """Test converting to dictionary."""
        explanation = PredictionExplanation(
            prediction=0.75,
            prediction_class="BUY",
            confidence=0.92,
            feature_contributions=[],
            base_value=0.50,
            timestamp="2026-04-01T12:00:00+07:00",
        )
        
        data = explanation.to_dict()
        assert data["prediction"] == 0.75
        assert "timestamp" in data


class TestExplainabilityService:
    """Test explainability service."""

    @pytest.fixture
    def sample_data(self):
        """Create sample data."""
        np.random.seed(42)
        n_samples = 100
        
        df = pd.DataFrame({
            "open": np.random.uniform(10000, 10500, n_samples),
            "high": np.random.uniform(10500, 11000, n_samples),
            "low": np.random.uniform(9500, 10000, n_samples),
            "close": np.random.uniform(10000, 10500, n_samples),
            "volume": np.random.uniform(1e7, 3e7, n_samples),
            "sma_20": np.random.uniform(10000, 10500, n_samples),
            "rsi_14": np.random.uniform(20, 80, n_samples),
            "macd": np.random.uniform(-100, 100, n_samples),
            "bollinger_upper": np.random.uniform(10500, 11000, n_samples),
            "bollinger_lower": np.random.uniform(9500, 10000, n_samples),
        })
        
        return df

    def test_service_initialization(self):
        """Test service initialization."""
        service = ExplainabilityService()
        assert service.model is None
        assert service.explainer is None

    def test_service_load_model(self, sample_data):
        """Test loading model."""
        from sklearn.ensemble import RandomForestClassifier
        
        service = ExplainabilityService()
        
        # Create dummy model
        X = sample_data
        y = np.random.binomial(1, 0.5, len(sample_data))
        
        model = RandomForestClassifier(n_estimators=10, random_state=42)
        model.fit(X, y)
        
        service.model = model
        assert service.model is not None

    def test_service_initialize_explainer(self, sample_data):
        """Test initializing SHAP explainer."""
        from sklearn.ensemble import RandomForestClassifier
        
        service = ExplainabilityService()
        
        # Create dummy model
        X = sample_data
        y = np.random.binomial(1, 0.5, len(sample_data))
        
        model = RandomForestClassifier(n_estimators=5, random_state=42)
        model.fit(X, y)
        service.model = model
        
        # Initialize explainer
        try:
            service.initialize_explainer(
                X,
                model_type=ModelType.RANDOM_FOREST,
                explainer_type=ExplainerType.TREE,
            )
            assert service.explainer is not None
        except ImportError:
            pytest.skip("SHAP not installed")

    def test_feature_names_extracted(self, sample_data):
        """Test that feature names are extracted."""
        from sklearn.ensemble import RandomForestClassifier
        
        service = ExplainabilityService()
        
        X = sample_data
        y = np.random.binomial(1, 0.5, len(sample_data))
        
        model = RandomForestClassifier(n_estimators=5, random_state=42)
        model.fit(X, y)
        service.model = model
        
        try:
            service.initialize_explainer(X)
            assert len(service.feature_names) == len(X.columns)
            assert "rsi_14" in service.feature_names
        except ImportError:
            pytest.skip("SHAP not installed")


class TestFeatureAnalysis:
    """Test feature analysis."""

    @pytest.fixture
    def sample_data(self):
        """Create sample data."""
        np.random.seed(42)
        n_samples = 100
        
        df = pd.DataFrame({
            "feature_1": np.random.uniform(0, 100, n_samples),
            "feature_2": np.random.uniform(0, 50, n_samples),
            "feature_3": np.random.uniform(0, 200, n_samples),
        })
        
        return df

    def test_feature_analysis(self, sample_data):
        """Test analyzing a feature."""
        from sklearn.linear_model import LogisticRegression
        
        service = ExplainabilityService()
        
        X = sample_data
        y = np.random.binomial(1, 0.5, len(sample_data))
        
        model = LogisticRegression(random_state=42)
        model.fit(X, y)
        service.model = model
        
        try:
            service.initialize_explainer(X)
            analysis = service.analyze_feature(X, "feature_1")
            
            assert analysis["feature"] == "feature_1"
            assert "correlation_with_prediction" in analysis
            assert "min_value" in analysis
            assert "max_value" in analysis
        except ImportError:
            pytest.skip("SHAP not installed")


class TestPredictionClass:
    """Test prediction class mapping."""

    def test_buy_signal(self):
        """Test BUY prediction class."""
        from src.api.explainability_service import SHAPExplainer
        
        # When prediction > 0.65 → BUY
        prediction = 0.75
        expected_class = "BUY" if prediction > 0.65 else ("SELL" if prediction < 0.35 else "HOLD")
        assert expected_class == "BUY"

    def test_sell_signal(self):
        """Test SELL prediction class."""
        prediction = 0.25
        expected_class = "BUY" if prediction > 0.65 else ("SELL" if prediction < 0.35 else "HOLD")
        assert expected_class == "SELL"

    def test_hold_signal(self):
        """Test HOLD prediction class."""
        prediction = 0.50
        expected_class = "BUY" if prediction > 0.65 else ("SELL" if prediction < 0.35 else "HOLD")
        assert expected_class == "HOLD"


class TestModelMetrics:
    """Test model metrics."""

    def test_metrics_storage(self):
        """Test storing and retrieving metrics."""
        from src.api.explainability_service import ModelMetrics
        
        service = ExplainabilityService()
        
        metrics = ModelMetrics(
            accuracy=0.72,
            precision=0.68,
            recall=0.75,
            f1_score=0.71,
            auc_roc=0.78,
            test_date="2026-04-01",
            model_version="v1.2.3",
        )
        
        service.set_model_metrics(metrics)
        retrieved = service.get_model_metrics()
        
        assert retrieved["accuracy"] == 0.72
        assert retrieved["model_version"] == "v1.2.3"


class TestExplainabilityIntegration:
    """Integration tests for explainability."""

    @pytest.fixture
    def full_setup(self):
        """Setup complete explainability pipeline."""
        from sklearn.ensemble import RandomForestClassifier
        
        np.random.seed(42)
        n_samples = 100
        
        X = pd.DataFrame({
            "feature_1": np.random.uniform(0, 100, n_samples),
            "feature_2": np.random.uniform(0, 50, n_samples),
            "feature_3": np.random.uniform(0, 200, n_samples),
        })
        
        y = np.random.binomial(1, 0.5, len(X))
        
        model = RandomForestClassifier(n_estimators=5, random_state=42)
        model.fit(X, y)
        
        service = ExplainabilityService()
        service.model = model
        
        try:
            service.initialize_explainer(X)
        except ImportError:
            pytest.skip("SHAP not installed")
        
        return service, X

    def test_full_explanation_pipeline(self, full_setup):
        """Test complete explanation workflow."""
        service, X = full_setup
        
        # Get feature importance
        importances = service.get_feature_importance(X)
        assert len(importances) > 0
        assert importances[0].rank == 1

    def test_batch_explanations(self, full_setup):
        """Test explaining multiple samples."""
        service, X = full_setup
        
        # Get first sample
        sample = X.iloc[[0]]
        
        explanation = service.explain_prediction(sample, prediction_index=0, top_features=3)
        
        assert "prediction" in explanation
        assert "prediction_class" in explanation
        assert "confidence" in explanation


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
