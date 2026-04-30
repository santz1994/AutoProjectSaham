"""
XAI (Explainable AI) API Routes
================================

REST endpoints for RL agent explainability — feature importance,
narrative generation, and history.

Endpoints:
- POST /api/xai/explain           – Compute feature importance + narrative
- GET  /api/xai/history           – Recent explanation history
- GET  /api/xai/stats             – XAI service statistics
- GET  /api/xai/health            – Service health check

Author: AutoSaham Team
Version: 1.0.0
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

import numpy as np
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/xai", tags=["xai"])

# Lazy singleton – avoids import-time failures when RL dependencies are absent.
_xai_service = None


def _get_xai_service():
    global _xai_service
    if _xai_service is None:
        try:
            from src.api.services.xai_service import XAIService
            _xai_service = XAIService()
        except Exception as exc:
            logger.error("XAI service init failed: %s", exc)
            raise HTTPException(status_code=503, detail=f"XAI service unavailable: {exc}")
    return _xai_service


# ---------------------------------------------------------------------------
# Request schemas
# ---------------------------------------------------------------------------

class ExplainRequest(BaseModel):
    """Request body for /api/xai/explain."""
    symbol: str = "BTC/USDT"
    action: str = "BUY"              # BUY | SELL | HOLD
    observation: Optional[List[float]] = None   # raw observation vector
    action_value: Optional[float] = None        # raw RL output (-1.0 … 1.0)
    target_fraction: Optional[float] = None     # computed portfolio fraction
    regime: str = "unknown"
    supervisor_flags: Optional[List[str]] = None
    stop_loss_distance: Optional[float] = None


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("/health")
async def xai_health():
    """Health probe."""
    try:
        svc = _get_xai_service()
        stats = svc.get_stats() if hasattr(svc, "get_stats") else {}
        return JSONResponse({"status": "ok", **stats})
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("XAI health error: %s", exc)
        raise HTTPException(status_code=503, detail=str(exc))


@router.post("/explain")
async def xai_explain(req: ExplainRequest):
    """
    Compute feature-importance explanation for the given *symbol* and *action*.

    Two modes:
    1. **With observation vector** – full permutation-based importance using XAIService.
    2. **Without observation**     – returns a placeholder narrative (service needs observation data).
    """
    try:
        svc = _get_xai_service()

        # Map action string → numeric value if not provided
        action_value = req.action_value
        if action_value is None:
            action_map = {"BUY": 0.7, "SELL": -0.7, "HOLD": 0.0}
            action_value = action_map.get(req.action.upper(), 0.0)

        target_fraction = req.target_fraction or abs(action_value) * 0.5

        # If observation provided → full pipeline
        if req.observation:
            obs = np.array(req.observation, dtype=np.float32)
            base_pred = action_value * 0.05  # simplified predicted return
            contributions = svc.compute_feature_importance(obs, base_pred)

            explanation = svc.generate_explanation(
                symbol=req.symbol,
                action_value=action_value,
                target_fraction=target_fraction,
                observation=obs,
                feature_contributions=contributions,
                regime=req.regime,
                supervisor_flags=req.supervisor_flags,
                stop_loss_distance=req.stop_loss_distance,
            )
            return JSONResponse(explanation.to_dict())

        # Fallback: return stats-only explanation
        stats = svc.get_stats()
        return JSONResponse({
            "symbol": req.symbol,
            "action": req.action.upper(),
            "action_value": action_value,
            "target_fraction": target_fraction,
            "narrative": (
                f"RL Agent recommends {req.action.upper()} {req.symbol}. "
                "Provide observation vector for full feature-importance analysis."
            ),
            "feature_contributions": [],
            "confidence_score": abs(action_value),
            "risk_assessment": "UNAVAILABLE — observation data required",
            "regime_context": req.regime,
            "supervisor_flags": req.supervisor_flags or [],
            "stats": stats,
        })

    except HTTPException:
        raise
    except Exception as exc:
        logger.error("XAI explain error (%s): %s", req.symbol, exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/history")
async def xai_history(limit: int = Query(20, ge=1, le=100)):
    """Return the most recent explanations."""
    try:
        svc = _get_xai_service()
        history = svc.get_history(limit=limit)
        return JSONResponse({"explanations": history, "total": len(history)})
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("XAI history error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/stats")
async def xai_stats():
    """Aggregate statistics (total explanations, etc.)."""
    try:
        svc = _get_xai_service()
        stats = svc.get_stats()
        return JSONResponse(stats)
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("XAI stats error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))