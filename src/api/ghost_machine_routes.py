"""
Ghost Machine API Routes
========================

REST endpoints for the autonomous trading loop orchestrator.

Endpoints:
- POST /api/ghost-machine/start  - Start autonomous loop
- POST /api/ghost-machine/stop   - Stop autonomous loop
- GET  /api/ghost-machine/status - Get loop status & stats
- POST /api/ghost-machine/cycle  - Trigger single cycle manually
- GET  /api/ghost-machine/history - Get recent cycle history
- GET  /api/ghost-machine/health - Health check

Author: AutoSaham Team
Version: 1.0.0
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/ghost-machine", tags=["ghost-machine"])

# Module-level singleton — initialized by server.py at startup
_ghost_machine = None
_anomaly_guard = None
_automl_pipeline = None


def init_ghost_machine_services(
    ghost_machine=None,
    anomaly_guard=None,
    automl_pipeline=None,
):
    """Called once from server.py startup to inject service references."""
    global _ghost_machine, _anomaly_guard, _automl_pipeline
    _ghost_machine = ghost_machine
    _anomaly_guard = anomaly_guard
    _automl_pipeline = automl_pipeline


class GhostMachineConfigRequest(BaseModel):
    """Request body for configuring Ghost Machine."""
    cycle_interval: Optional[int] = None
    live_mode: Optional[bool] = None
    symbols: Optional[list] = None
    max_consecutive_errors: Optional[int] = None
    error_cooldown: Optional[int] = None


# ─── Ghost Machine Control ──────────────────────────────────────────────────

@router.get("/health")
async def health_check():
    """Check Ghost Machine service health."""
    return {
        "status": "healthy" if _ghost_machine else "not_initialized",
        "ghost_machine_running": _ghost_machine.is_running if _ghost_machine else False,
        "anomaly_guard_active": _anomaly_guard is not None,
        "automl_active": _automl_pipeline is not None,
    }


@router.get("/status")
async def get_status():
    """Get Ghost Machine status and statistics."""
    if not _ghost_machine:
        raise HTTPException(status_code=503, detail="Ghost Machine not initialized")
    
    return {
        "running": _ghost_machine.is_running,
        "config": {
            "symbols": _ghost_machine.config.symbols,
            "cycle_interval": _ghost_machine.config.cycle_interval,
            "live_mode": _ghost_machine.config.live_mode,
        },
        "stats": _ghost_machine.stats,
    }


@router.post("/start")
async def start_ghost_machine():
    """Start the autonomous trading loop."""
    if not _ghost_machine:
        raise HTTPException(status_code=503, detail="Ghost Machine not initialized")
    
    if _ghost_machine.is_running:
        return {"status": "already_running", "message": "Ghost Machine is already running"}
    
    _ghost_machine.start()
    logger.info("Ghost Machine started via API")
    return {"status": "started", "message": "Ghost Machine autonomous loop started"}


@router.post("/stop")
async def stop_ghost_machine():
    """Stop the autonomous trading loop."""
    if not _ghost_machine:
        raise HTTPException(status_code=503, detail="Ghost Machine not initialized")
    
    if not _ghost_machine.is_running:
        return {"status": "not_running", "message": "Ghost Machine is not running"}
    
    _ghost_machine.stop()
    logger.info("Ghost Machine stopped via API")
    return {"status": "stopped", "message": "Ghost Machine autonomous loop stopped"}


@router.post("/cycle")
async def trigger_single_cycle():
    """Trigger a single trading cycle manually."""
    if not _ghost_machine:
        raise HTTPException(status_code=503, detail="Ghost Machine not initialized")
    
    results = _ghost_machine.run_single_cycle()
    return {
        "status": "cycle_completed",
        "results": [
            r.to_dict() if hasattr(r, "to_dict") else r
            for r in (results or [])
        ],
    }


@router.get("/history")
async def get_history(limit: int = Query(default=20, ge=1, le=100)):
    """Get recent cycle history."""
    if not _ghost_machine:
        raise HTTPException(status_code=503, detail="Ghost Machine not initialized")
    
    history = _ghost_machine.cycle_history[-limit:]
    return {
        "count": len(history),
        "cycles": [
            {
                "cycle_id": getattr(r, "cycle_id", None)
                or f"{getattr(r, 'timestamp', '')}-{getattr(r, 'symbol', '')}-{idx}",
                "timestamp": getattr(r, "timestamp", None),
                "symbol": getattr(r, "symbol", None),
                "total_trades_executed": 1 if getattr(r, "action_taken", None) in ("BUY", "SELL") else 0,
                "total_trades_blocked": 1 if getattr(r, "action_taken", None) == "BLOCKED" else 0,
                "execution_time_ms": None,
                "error": getattr(r, "error", None),
            }
            for idx, r in enumerate(history)
        ],
    }


# ─── Anomaly Guard Control ──────────────────────────────────────────────────

@router.get("/anomaly-guard/status")
async def get_anomaly_guard_status():
    """Get anomaly guard status and statistics."""
    if not _anomaly_guard:
        raise HTTPException(status_code=503, detail="Anomaly Guard not initialized")

    raw_stats = (
        _anomaly_guard.get_stats()
        if hasattr(_anomaly_guard, "get_stats")
        else getattr(_anomaly_guard, "stats", {})
    )
    checks = raw_stats.get("total_evaluations", raw_stats.get("checks", 0))
    vetoes = raw_stats.get("veto_count", 0) + raw_stats.get("mimo_veto_count", 0)
    reductions = raw_stats.get("reduce_count", 0)

    return {
        "active": True,
        "stats": {
            **raw_stats,
            "checks": checks,
            "vetoes": vetoes,
            "reductions": reductions,
        },
        "config": {
            "veto_threshold": getattr(_anomaly_guard, "veto_threshold", None),
            "reduce_threshold": getattr(_anomaly_guard, "reduce_threshold", None),
            "min_risk_multiplier": getattr(_anomaly_guard, "min_risk_multiplier", None),
            "enable_mimo_veto": getattr(_anomaly_guard, "enable_mimo_veto", None),
        },
    }


@router.get("/anomaly-guard/history")
async def get_anomaly_guard_history(limit: int = Query(default=20, ge=1, le=100)):
    """Get recent anomaly guard decisions."""
    if not _anomaly_guard:
        raise HTTPException(status_code=503, detail="Anomaly Guard not initialized")

    if hasattr(_anomaly_guard, "get_recent_blocks"):
        history = _anomaly_guard.get_recent_blocks(limit)
    else:
        raw_history = getattr(_anomaly_guard, "history", []) or []
        history = [
            r.to_dict() if hasattr(r, "to_dict") else r
            for r in raw_history[-limit:]
        ]
    return {"count": len(history), "decisions": history}


# ─── AutoML Control ─────────────────────────────────────────────────────────

@router.get("/automl/status")
async def get_automl_status():
    """Get continuous AutoML pipeline status."""
    if not _automl_pipeline:
        raise HTTPException(status_code=503, detail="AutoML Pipeline not initialized")

    stats = (
        _automl_pipeline.get_stats()
        if hasattr(_automl_pipeline, "get_stats")
        else getattr(_automl_pipeline, "stats", {})
    )
    registry = None
    registry_obj = getattr(_automl_pipeline, "registry", None)
    if registry_obj is not None:
        models = (
            registry_obj.get_all_models()
            if hasattr(registry_obj, "get_all_models")
            else []
        )
        registry = {
            "total_models": len(models),
            "production_model": (
                registry_obj.get_production_model()
                if hasattr(registry_obj, "get_production_model")
                else None
            ),
        }

    return {
        "active": True,
        "stats": stats,
        "registry": registry,
    }


@router.post("/automl/trigger")
async def trigger_automl():
    """Trigger an immediate AutoML optimization run."""
    if not _automl_pipeline:
        raise HTTPException(status_code=503, detail="AutoML Pipeline not initialized")
    
    try:
        result = _automl_pipeline.run_optimization()
        return {"status": "completed", "result": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AutoML run failed: {e}")


@router.get("/automl/models")
async def list_automl_models():
    """List all registered models in the AutoML registry."""
    if not _automl_pipeline or not _automl_pipeline.registry:
        raise HTTPException(status_code=503, detail="AutoML Registry not initialized")

    return _automl_pipeline.registry.get_all_models()