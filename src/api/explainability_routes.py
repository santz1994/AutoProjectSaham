"""
Explainability API Routes
===========================

REST endpoints for model explainability and SHAP-based explanations.

Endpoints:
- GET /api/explainability/features - Get feature importance
- POST /api/explainability/explain - Explain a prediction
- GET /api/explainability/feature/{name} - Analyze specific feature
- GET /api/explainability/metrics - Get model metrics
- GET /api/explainability/health - Service health check

Author: AutoSaham Team
Version: 1.0.0
"""

import logging
from typing import Optional, List

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from fastapi.responses import JSONResponse
import pandas as pd

from src.api.explainability_service import (
    get_explainability_service,
    ModelType,
    ExplainerType,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/explainability", tags=["explainability"])


class ExplanationRequest(BaseModel):
    """Request to explain a prediction."""
    features: dict  # Feature values as {"feature_name": value, ...}
    top_features: int = 10


class ExplanationResponse(BaseModel):
    """Explanation response."""
    prediction: float
    prediction_class: str  # BUY, HOLD, SELL
    confidence: float
    feature_contributions: List[dict]
    base_value: float
    timestamp: str


@router.get("/health")
async def health_check():
    """
    Check explainability service health.
    
    Returns:
        Health status
        
    Example:
        GET /api/explainability/health
    """
    try:
        service = get_explainability_service()
        
        is_healthy = (
            service.model is not None and
            service.explainer is not None
        )
        
        return JSONResponse({
            "status": "healthy" if is_healthy else "degraded",
            "model_loaded": service.model is not None,
            "explainer_initialized": service.explainer is not None,
            "features_count": len(service.feature_names),
        })
    
    except Exception as e:
        logger.error(f"Health check error: {str(e)}")
        raise HTTPException(status_code=503, detail=str(e))


@router.get("/features")
async def get_feature_importance(limit: int = Query(20, ge=1, le=100)):
    """
    Get feature importance ranking.
    
    Args:
        limit: Number of top features to return
        
    Returns:
        Ranked list of features with importance scores
        
    Example:
        GET /api/explainability/features?limit=10
        
        Response:
        [
            {
                "feature_name": "volume_5d_sma",
                "importance_value": 0.125,
                "importance_percent": 12.5,
                "rank": 1
            },
            ...
        ]
    """
    try:
        service = get_explainability_service()
        
        if service.explainer is None:
            raise HTTPException(
                status_code=503,
                detail="Explainer not initialized"
            )
        
        importances = service.get_feature_importance()
        
        # Return top features
        return JSONResponse([
            imp for imp in importances[:limit]
        ])
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting feature importance: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/explain")
async def explain_prediction(request: ExplanationRequest):
    """
    Explain a model prediction.
    
    Args:
        request: Features and configuration
        
    Returns:
        Explanation with SHAP values and feature contributions
        
    Example:
        POST /api/explainability/explain
        
        Request:
        {
            "features": {
                "open": 10250.0,
                "high": 10450.0,
                "low": 10200.0,
                "close": 10400.0,
                "volume": 25000000,
                ...
            },
            "top_features": 10
        }
        
        Response:
        {
            "prediction": 0.65,
            "prediction_class": "BUY",
            "confidence": 0.92,
            "feature_contributions": [
                {
                    "feature": "rsi_14",
                    "shap_value": 0.045,
                    "feature_value": 65.2
                },
                ...
            ],
            "base_value": 0.50,
            "timestamp": "2026-04-01T12:45:00+07:00"
        }
    """
    try:
        service = get_explainability_service()
        
        if service.explainer is None:
            raise HTTPException(
                status_code=503,
                detail="Explainer not initialized"
            )
        
        # Create DataFrame from features
        df = pd.DataFrame([request.features])
        
        # Explain prediction
        explanation = service.explain_prediction(
            df,
            prediction_index=0,
            top_features=request.top_features
        )
        
        return JSONResponse(explanation)
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error explaining prediction: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/feature/{feature_name}")
async def analyze_feature(feature_name: str):
    """
    Analyze how a feature affects model predictions.
    
    Args:
        feature_name: Name of feature to analyze
        
    Returns:
        Feature analysis with statistics
        
    Example:
        GET /api/explainability/feature/rsi_14
        
        Response:
        {
            "feature": "rsi_14",
            "correlation_with_prediction": 0.45,
            "min_value": 20.5,
            "max_value": 80.3,
            "mean_value": 50.2,
            "std_value": 15.4,
            "data_type": "float64"
        }
    """
    try:
        service = get_explainability_service()
        
        if feature_name not in service.feature_names:
            raise HTTPException(
                status_code=404,
                detail=f"Feature '{feature_name}' not found in model"
            )
        
        analysis = service.analyze_feature(
            service.explainer.training_data,
            feature_name
        )
        
        return JSONResponse(analysis)
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error analyzing feature {feature_name}: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/metrics")
async def get_model_metrics():
    """
    Get model performance metrics.
    
    Returns:
        Model accuracy, precision, recall, F1, AUC-ROC
        
    Example:
        GET /api/explainability/metrics
        
        Response:
        {
            "accuracy": 0.72,
            "precision": 0.68,
            "recall": 0.75,
            "f1_score": 0.71,
            "auc_roc": 0.78,
            "test_date": "2026-04-01T12:00:00+07:00",
            "model_version": "v1.2.3"
        }
    """
    try:
        service = get_explainability_service()
        metrics = service.get_model_metrics()
        
        if not metrics:
            raise HTTPException(
                status_code=404,
                detail="Model metrics not available"
            )
        
        return JSONResponse(metrics)
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting model metrics: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/supported-features")
async def get_supported_features():
    """
    Get list of features the model uses.
    
    Returns:
        List of feature names and their properties
        
    Example:
        GET /api/explainability/supported-features
        
        Response:
        {
            "features": [
                "open",
                "high",
                "low",
                "close",
                "volume",
                "sma_20",
                "rsi_14",
                ...
            ],
            "total": 35
        }
    """
    try:
        service = get_explainability_service()
        
        return JSONResponse({
            "features": service.feature_names,
            "total": len(service.feature_names),
        })
    
    except Exception as e:
        logger.error(f"Error getting supported features: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


# Setup routes
def setup_explainability_routes(app):
    """
    Setup explainability routes to FastAPI app.
    
    Args:
        app: FastAPI application instance
    """
    app.include_router(router)
    logger.info("Explainability routes configured")
