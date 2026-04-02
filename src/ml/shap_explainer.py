"""SHAP explainability for ML model predictions.

Generates SHAP values showing which features most influence buy/sell signals.
"""

import numpy as np
from typing import Dict, List, Any, Optional


def generate_shap_explanation(
    model,
    feature_row: np.ndarray,
    feature_names: List[str],
    top_k: int = 3,
) -> List[Dict[str, Any]]:
    """
    Generate SHAP-based explanation for a model prediction.
    
    Args:
        model: Trained sklearn/LightGBM model
        feature_row: Single sample [1, n_features]
        feature_names: Feature column names
        top_k: Number of top features to return
    
    Returns:
        List[{"feature": str, "weight": float}] - Top-k features by impact.
    """
    try:
        import shap
    except ImportError:
        return [{"feature": "N/A", "weight": 0.0, "error": "SHAP not installed"}]
    
    try:
        # Detect model type and use appropriate explainer
        explainer = None
        shap_values = None
        
        # TreeExplainer: LightGBM, XGBoost, sklearn tree models
        try:
            explainer = shap.TreeExplainer(model)
            shap_values = explainer.shap_values(feature_row)
            if isinstance(shap_values, list):
                # Multi-class or binary with list output
                shap_values = shap_values[1] if len(shap_values) > 1 else shap_values[0]
        except Exception:
            # Fallback: KernelExplainer (slower, works for any model)
            explainer = shap.KernelExplainer(
                model.predict_proba if hasattr(model, 'predict_proba') else model.predict,
                shap.sample(feature_row, 50)  # Sample 50 background instances
            )
            shap_values = explainer.shap_values(feature_row)[1]  # Class 1 (positive)
        
        # Sort by absolute impact
        impacts = list(zip(feature_names, np.abs(shap_values[0] if len(shap_values.shape) > 1 else shap_values)))
        top_features = sorted(impacts, key=lambda x: x[1], reverse=True)[:top_k]
        
        return [
            {
                "feature": name,
                "weight": float(round(weight, 4)),
                "impact": "positive" if shap_values[feature_names.index(name)] > 0 else "negative"
            }
            for name, weight in top_features
        ]
    
    except Exception as e:
        return [{"feature": "Error", "weight": 0.0, "error": str(e)}]


def format_explanation_for_frontend(explanation: List[Dict], signal: str = "BUY") -> Dict:
    """Format SHAP explanation into frontend-friendly JSON.
    
    Args:
        explanation: List of SHAP feature explanations
        signal: Predicted signal (BUY, SELL, HOLD)
    
    Returns:
        {"decision": signal, "shap": [...], "confidence": float}
    """
    return {
        "decision": signal,
        "shap": explanation,
        "explanation": f"Top factors driving {signal} signal: " + ", ".join(
            [f"{e['feature']} ({e['impact']})" for e in explanation[:3]]
        ),
    }
