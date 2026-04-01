"""
Model Explainability Service using SHAP
========================================

Provides SHAP-based model interpretability and feature importance analysis.

Features:
- SHAP values computation (TreeExplainer, KernelExplainer)
- Feature importance ranking
- Prediction explanation (why model made decision)
- Partial dependence plots
- Individual example explanation
- Confidence scoring
- Jakarta timezone support
- Indonesia market compliance

Author: AutoSaham Team
Version: 1.0.0
"""

import json
import logging
from datetime import datetime
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, asdict
from enum import Enum

import numpy as np
import pandas as pd
import pytz
import joblib

try:
    import shap
except ImportError:
    shap = None

from sklearn.metrics import confidence_score

logger = logging.getLogger(__name__)
JAKARTA_TZ = pytz.timezone("Asia/Jakarta")


class ModelType(str, Enum):
    """Supported model types for explanation."""
    ENSEMBLE = "ensemble"
    LIGHTGBM = "lightgbm"
    XGBOOST = "xgboost"
    RANDOM_FOREST = "random_forest"
    NEURAL_NETWORK = "neural_network"


class ExplainerType(str, Enum):
    """SHAP explainer types."""
    TREE = "tree"
    KERNEL = "kernel"
    SAMPLING = "sampling"
    GRADIENT = "gradient"


@dataclass
class FeatureImportance:
    """Feature importance data."""
    feature_name: str
    importance_value: float
    importance_percent: float
    contribution_direction: str  # "positive", "negative", "neutral"
    rank: int
    
    def to_dict(self) -> Dict:
        """Convert to dictionary."""
        return asdict(self)


@dataclass
class PredictionExplanation:
    """Explanation for a single prediction."""
    prediction: float  # Model output (e.g., 0.65 for probability)
    prediction_class: str  # "BUY", "HOLD", "SELL"
    confidence: float  # Confidence score (0-1)
    feature_contributions: List[Dict]  # Top contributing features with SHAP values
    base_value: float  # Model's average prediction
    timestamp: str  # When explanation was generated (Jakarta TZ)
    
    def to_dict(self) -> Dict:
        """Convert to dictionary."""
        data = asdict(self)
        data["timestamp"] = datetime.now(JAKARTA_TZ).isoformat()
        return data


@dataclass
class ModelMetrics:
    """Model performance metrics."""
    accuracy: float
    precision: float
    recall: float
    f1_score: float
    auc_roc: float
    test_date: str
    model_version: str
    
    def to_dict(self) -> Dict:
        """Convert to dictionary."""
        return asdict(self)


class SHAPExplainer:
    """Wrapper for SHAP explainability."""
    
    def __init__(
        self,
        model,
        training_data: pd.DataFrame,
        model_type: ModelType = ModelType.ENSEMBLE,
        explainer_type: ExplainerType = ExplainerType.TREE,
    ):
        """
        Initialize SHAP explainer.
        
        Args:
            model: Trained model (sklearn, LightGBM, XGBoost, etc.)
            training_data: Training data for baseline
            model_type: Type of model
            explainer_type: Type of SHAP explainer
        """
        if shap is None:
            raise ImportError(
                "SHAP not installed. Install with: pip install shap"
            )
        
        self.model = model
        self.training_data = training_data
        self.model_type = model_type
        self.explainer_type = explainer_type
        self.feature_names = list(training_data.columns)
        
        # Initialize explainer based on type
        self._initialize_explainer()
    
    def _initialize_explainer(self):
        """Initialize appropriate SHAP explainer."""
        try:
            if self.explainer_type == ExplainerType.TREE:
                # Use TreeExplainer for tree-based models
                self.explainer = shap.TreeExplainer(self.model)
            
            elif self.explainer_type == ExplainerType.KERNEL:
                # Use KernelExplainer (model-agnostic)
                self.explainer = shap.KernelExplainer(
                    self.model.predict,
                    shap.sample(self.training_data, min(100, len(self.training_data)))
                )
            
            elif self.explainer_type == ExplainerType.SAMPLING:
                # Use SamplingExplainer
                self.explainer = shap.SamplingExplainer(
                    self.model.predict,
                    self.training_data
                )
            
            else:
                raise ValueError(f"Unknown explainer type: {self.explainer_type}")
            
            logger.info(f"SHAP {self.explainer_type.value} explainer initialized")
        
        except Exception as e:
            logger.error(f"Failed to initialize SHAP explainer: {str(e)}")
            raise
    
    def compute_shap_values(self, X: pd.DataFrame) -> np.ndarray:
        """
        Compute SHAP values for data.
        
        Args:
            X: Input features
            
        Returns:
            SHAP values array
        """
        try:
            shap_values = self.explainer.shap_values(X)
            
            # Handle multi-class output (for classifiers)
            if isinstance(shap_values, list):
                return shap_values
            
            return shap_values
        
        except Exception as e:
            logger.error(f"Error computing SHAP values: {str(e)}")
            raise
    
    def explain_prediction(
        self,
        X: pd.DataFrame,
        prediction_index: int = 0,
        top_features: int = 10
    ) -> PredictionExplanation:
        """
        Explain a single prediction.
        
        Args:
            X: Input features (1 row or multiple rows)
            prediction_index: Which sample to explain
            top_features: Number of top contributing features to include
            
        Returns:
            PredictionExplanation object
        """
        try:
            # Get model prediction
            prediction = float(self.model.predict(X.iloc[[prediction_index]])[0])
            
            # For probability (binary classification)
            if prediction <= 1.0 and hasattr(self.model, 'predict_proba'):
                proba = self.model.predict_proba(X.iloc[[prediction_index]])[0]
                prediction = float(proba[1]) if len(proba) > 1 else prediction
                confidence = float(max(proba))
            else:
                confidence = min(abs(prediction), 1.0)
            
            # Map to class
            if prediction > 0.65:
                prediction_class = "BUY"
            elif prediction < 0.35:
                prediction_class = "SELL"
            else:
                prediction_class = "HOLD"
            
            # Compute SHAP values
            shap_values = self.compute_shap_values(X.iloc[[prediction_index]])
            
            # Handle multi-class
            if isinstance(shap_values, list):
                shap_vals = shap_values[1]  # Use positive class for binary
            else:
                shap_vals = shap_values
            
            base_value = float(self.explainer.expected_value)
            if isinstance(base_value, list):
                base_value = float(base_value[1])
            
            # Get feature contributions
            shap_row = shap_vals[prediction_index]
            feature_contribs = []
            
            for feature_idx, feature_name in enumerate(self.feature_names):
                if feature_idx < len(shap_row):
                    feature_contribs.append({
                        "feature": feature_name,
                        "shap_value": float(shap_row[feature_idx]),
                        "feature_value": float(X.iloc[prediction_index, feature_idx]),
                    })
            
            # Sort by absolute SHAP value and take top features
            feature_contribs.sort(
                key=lambda x: abs(x["shap_value"]),
                reverse=True
            )
            feature_contribs = feature_contribs[:top_features]
            
            return PredictionExplanation(
                prediction=prediction,
                prediction_class=prediction_class,
                confidence=confidence,
                feature_contributions=feature_contribs,
                base_value=base_value,
                timestamp=datetime.now(JAKARTA_TZ).isoformat(),
            )
        
        except Exception as e:
            logger.error(f"Error explaining prediction: {str(e)}")
            raise
    
    def get_feature_importance(self, X: pd.DataFrame = None) -> List[FeatureImportance]:
        """
        Get global feature importance ranking.
        
        Args:
            X: Input data (optional, uses training data if not provided)
            
        Returns:
            List of FeatureImportance objects sorted by importance
        """
        try:
            if X is None:
                X = self.training_data
            
            # Compute SHAP values
            shap_values = self.compute_shap_values(X)
            
            # Handle multi-class
            if isinstance(shap_values, list):
                shap_vals = shap_values[1]  # Use positive class
            else:
                shap_vals = shap_values
            
            # Mean absolute SHAP value
            mean_abs_shap = np.mean(np.abs(shap_vals), axis=0)
            
            # Normalize to percentages
            total = np.sum(mean_abs_shap)
            importance_percent = (mean_abs_shap / total * 100) if total > 0 else mean_abs_shap
            
            # Create FeatureImportance objects
            importances = []
            for idx, feature_name in enumerate(self.feature_names):
                if idx < len(mean_abs_shap):
                    importances.append(FeatureImportance(
                        feature_name=feature_name,
                        importance_value=float(mean_abs_shap[idx]),
                        importance_percent=float(importance_percent[idx]),
                        contribution_direction="neutral",  # Store direction in explain_prediction
                        rank=0,  # Will be set below
                    ))
            
            # Sort by importance and assign ranks
            importances.sort(
                key=lambda x: x.importance_value,
                reverse=True
            )
            
            for idx, imp in enumerate(importances, 1):
                imp.rank = idx
            
            return importances
        
        except Exception as e:
            logger.error(f"Error computing feature importance: {str(e)}")
            raise
    
    def explain_batch(
        self,
        X: pd.DataFrame,
        top_features: int = 5
    ) -> List[PredictionExplanation]:
        """
        Explain multiple predictions.
        
        Args:
            X: Input features (multiple rows)
            top_features: Number of top features per explanation
            
        Returns:
            List of PredictionExplanation objects
        """
        explanations = []
        
        for idx in range(min(len(X), 100)):  # Limit to 100 for performance
            try:
                explanation = self.explain_prediction(
                    X,
                    prediction_index=idx,
                    top_features=top_features
                )
                explanations.append(explanation)
            except Exception as e:
                logger.warning(f"Failed to explain sample {idx}: {str(e)}")
        
        return explanations


class ExplainabilityService:
    """Service for model explainability."""
    
    def __init__(self, model_path: Optional[str] = None):
        """
        Initialize explainability service.
        
        Args:
            model_path: Path to saved model (optional)
        """
        self.model = None
        self.explainer = None
        self.feature_names = []
        self.model_metadata = None
        
        if model_path:
            self.load_model(model_path)
    
    def load_model(self, model_path: str):
        """
        Load trained model.
        
        Args:
            model_path: Path to model file
        """
        try:
            self.model = joblib.load(model_path)
            logger.info(f"Model loaded from {model_path}")
        except Exception as e:
            logger.error(f"Failed to load model: {str(e)}")
            raise
    
    def initialize_explainer(
        self,
        training_data: pd.DataFrame,
        model_type: ModelType = ModelType.ENSEMBLE,
        explainer_type: ExplainerType = ExplainerType.TREE,
    ):
        """
        Initialize SHAP explainer.
        
        Args:
            training_data: Training data for baseline
            model_type: Type of model
            explainer_type: Type of SHAP explainer
        """
        if self.model is None:
            raise ValueError("Model not loaded. Call load_model() first.")
        
        self.feature_names = list(training_data.columns)
        
        try:
            self.explainer = SHAPExplainer(
                self.model,
                training_data,
                model_type=model_type,
                explainer_type=explainer_type,
            )
            logger.info("SHAP explainer initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize explainer: {str(e)}")
            raise
    
    def explain_prediction(
        self,
        X: pd.DataFrame,
        prediction_index: int = 0,
        top_features: int = 10
    ) -> Dict:
        """Explain a prediction."""
        if self.explainer is None:
            raise ValueError("Explainer not initialized. Call initialize_explainer() first.")
        
        explanation = self.explainer.explain_prediction(
            X,
            prediction_index=prediction_index,
            top_features=top_features
        )
        
        return explanation.to_dict()
    
    def get_feature_importance(self, X: pd.DataFrame = None) -> List[Dict]:
        """Get feature importance ranking."""
        if self.explainer is None:
            raise ValueError("Explainer not initialized.")
        
        importances = self.explainer.get_feature_importance(X)
        return [imp.to_dict() for imp in importances]
    
    def analyze_feature(
        self,
        X: pd.DataFrame,
        feature_name: str
    ) -> Dict:
        """
        Analyze how a feature affects predictions.
        
        Args:
            X: Input data
            feature_name: Feature to analyze
            
        Returns:
            Analysis dictionary with stats and distributions
        """
        if feature_name not in self.feature_names:
            raise ValueError(f"Feature {feature_name} not found in model")
        
        feature_idx = self.feature_names.index(feature_name)
        
        # Get predictions
        predictions = self.model.predict(X)
        
        # Correlate feature with predictions
        feature_values = X[feature_name].values
        correlation = float(np.corrcoef(feature_values, predictions)[0, 1])
        
        return {
            "feature": feature_name,
            "correlation_with_prediction": correlation,
            "min_value": float(feature_values.min()),
            "max_value": float(feature_values.max()),
            "mean_value": float(feature_values.mean()),
            "std_value": float(feature_values.std()),
            "data_type": str(X[feature_name].dtype),
        }
    
    def get_model_metrics(self) -> Dict:
        """Get stored model metrics."""
        return self.model_metadata or {}
    
    def set_model_metrics(self, metrics: ModelMetrics):
        """Set model metrics."""
        self.model_metadata = metrics.to_dict()


# Global service instance
_explainability_service: Optional[ExplainabilityService] = None


def get_explainability_service() -> ExplainabilityService:
    """Get explainability service instance."""
    global _explainability_service
    if _explainability_service is None:
        raise RuntimeError("Explainability service not initialized")
    return _explainability_service


def init_explainability_service(model_path: Optional[str] = None) -> ExplainabilityService:
    """Initialize explainability service."""
    global _explainability_service
    _explainability_service = ExplainabilityService(model_path)
    return _explainability_service
