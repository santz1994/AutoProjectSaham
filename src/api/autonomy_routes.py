"""
Autonomy Control API Routes
============================

REST endpoints for trading autonomy level management,
kill-switch control, and pending order approval/rejection.

Endpoints:
- GET   /api/autonomy/status          – Current autonomy state
- POST  /api/autonomy/level           – Set autonomy level (1/2/3)
- POST  /api/autonomy/kill-switch     – Activate kill-switch
- DELETE /api/autonomy/kill-switch     – Deactivate kill-switch
- GET   /api/autonomy/pending-orders  – List pending orders (Level 2)
- POST  /api/autonomy/approve/{id}    – Approve pending order
- POST  /api/autonomy/reject/{id}     – Reject pending order
- POST  /api/autonomy/signal          – Process a trade signal
- GET   /api/autonomy/stats           – Service statistics
- GET   /api/autonomy/health          – Service health check

Author: AutoSaham Team
Version: 1.0.0
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/autonomy", tags=["autonomy"])

# Lazy singleton – avoids import-time failures when dependencies are absent.
_autonomy_service = None


def _get_autonomy_service():
    global _autonomy_service
    if _autonomy_service is None:
        try:
            from src.api.services.autonomy_service import AutonomyService
            _autonomy_service = AutonomyService()
        except Exception as exc:
            logger.error("Autonomy service init failed: %s", exc)
            raise HTTPException(status_code=503, detail=f"Autonomy service unavailable: {exc}")
    return _autonomy_service


# ---------------------------------------------------------------------------
# Request schemas
# ---------------------------------------------------------------------------

class SetLevelRequest(BaseModel):
    level: int = 1                   # 1=SIGNAL_ONLY, 2=HUMAN_CONFIRM, 3=FULL_AUTO
    admin_token: Optional[str] = None


class KillSwitchRequest(BaseModel):
    reason: str = "Manual activation via API"


class RejectRequest(BaseModel):
    reason: str = ""


class TradeSignalRequest(BaseModel):
    symbol: str = "BTC/USDT"
    action: str = "BUY"              # BUY | SELL | HOLD
    target_fraction: float = 0.0
    source: str = "rl_agent"
    metadata: Optional[Dict[str, Any]] = None


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("/health")
async def autonomy_health():
    """Health probe."""
    try:
        svc = _get_autonomy_service()
        stats = svc.get_stats()
        return JSONResponse({"status": "ok", **stats})
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Autonomy health error: %s", exc)
        raise HTTPException(status_code=503, detail=str(exc))


@router.get("/status")
async def autonomy_status():
    """Get current autonomy system state (level, kill-switch, pending count)."""
    try:
        svc = _get_autonomy_service()
        state = svc.get_state()
        return JSONResponse({
            "level": state.level.value,
            "level_name": state.level.name,
            "kill_switch_active": state.kill_switch_active,
            "pending_orders_count": state.pending_orders_count,
            "total_signals_processed": state.total_signals_processed,
            "total_orders_approved": state.total_orders_approved,
            "total_orders_rejected": state.total_orders_rejected,
            "last_level_change": state.last_level_change,
        })
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Autonomy status error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/level")
async def set_autonomy_level(req: SetLevelRequest):
    """
    Change the autonomy level.

    Levels:
    - 1 (SIGNAL_ONLY):   AI only generates signals, no orders.
    - 2 (HUMAN_CONFIRM): AI creates order drafts, requires manual approval.
    - 3 (FULL_AUTO):     AI executes directly without human intervention.
    """
    try:
        svc = _get_autonomy_service()
        result = svc.set_level(level=req.level, admin_token=req.admin_token)
        return JSONResponse(result)
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Set autonomy level error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/kill-switch")
async def activate_kill_switch(req: KillSwitchRequest):
    """Activate the emergency kill-switch: halt all trading immediately."""
    try:
        svc = _get_autonomy_service()
        result = svc.activate_kill_switch(reason=req.reason)
        return JSONResponse(result)
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Activate kill-switch error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.delete("/kill-switch")
async def deactivate_kill_switch():
    """Deactivate the kill-switch and resume normal operations."""
    try:
        svc = _get_autonomy_service()
        result = svc.deactivate_kill_switch()
        return JSONResponse(result)
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Deactivate kill-switch error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/pending-orders")
async def get_pending_orders():
    """List all pending orders (visible when autonomy = Level 2)."""
    try:
        svc = _get_autonomy_service()
        orders = svc.get_pending_orders()
        return JSONResponse({"pending_orders": orders, "total": len(orders)})
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Get pending orders error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/approve/{order_id}")
async def approve_order(order_id: str):
    """Approve a pending order (Level 2 human-in-the-loop)."""
    try:
        svc = _get_autonomy_service()
        result = svc.approve_order(order_id=order_id)
        return JSONResponse(result)
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Approve order error (%s): %s", order_id, exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/reject/{order_id}")
async def reject_order(order_id: str, req: RejectRequest = RejectRequest()):
    """Reject a pending order (Level 2 human-in-the-loop)."""
    try:
        svc = _get_autonomy_service()
        result = svc.reject_order(order_id=order_id, reason=req.reason)
        return JSONResponse(result)
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Reject order error (%s): %s", order_id, exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/signal")
async def process_trade_signal(req: TradeSignalRequest):
    """
    Submit a trade signal through the autonomy pipeline.

    The result depends on the current autonomy level:
    - Level 1: returns signal acknowledgement only
    - Level 2: creates a pending order for human approval
    - Level 3: executes the order immediately
    """
    try:
        svc = _get_autonomy_service()
        result = svc.process_trade_signal(
            symbol=req.symbol,
            action=req.action,
            target_fraction=req.target_fraction,
            source=req.source,
            metadata=req.metadata,
        )
        return JSONResponse(result)
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Process trade signal error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/stats")
async def autonomy_stats():
    """Aggregate statistics."""
    try:
        svc = _get_autonomy_service()
        stats = svc.get_stats()
        return JSONResponse(stats)
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Autonomy stats error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))