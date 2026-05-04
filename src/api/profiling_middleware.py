"""
Profiling Middleware – Request Timing & Performance Monitoring (Phase 7.2)

Adds X-Process-Time header to every response and logs slow requests.
Collects aggregate stats accessible via /api/v1/profiling/stats.
"""
from __future__ import annotations

import logging
import threading
import time
from collections import defaultdict
from typing import Any, Dict

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

logger = logging.getLogger(__name__)

# ─── Aggregate Stats ───
_stats_lock = threading.Lock()
_stats: Dict[str, Dict[str, Any]] = defaultdict(lambda: {
    "count": 0,
    "total_ms": 0.0,
    "max_ms": 0.0,
    "min_ms": float("inf"),
    "slow_count": 0,  # > 1000ms
})
_slow_threshold_ms = 1000.0


def get_profiling_stats() -> Dict[str, Any]:
    """Return aggregate profiling stats for all endpoints."""
    with _stats_lock:
        result = {}
        for path, data in sorted(_stats.items(), key=lambda x: -x[1]["total_ms"]):
            count = data["count"]
            if count == 0:
                continue
            result[path] = {
                "requests": count,
                "avg_ms": round(data["total_ms"] / count, 2),
                "max_ms": round(data["max_ms"], 2),
                "min_ms": round(data["min_ms"], 2) if data["min_ms"] < float("inf") else 0,
                "total_ms": round(data["total_ms"], 2),
                "slow_requests": data["slow_count"],
            }
        return {
            "endpoints": result,
            "slow_threshold_ms": _slow_threshold_ms,
            "total_endpoints_tracked": len(result),
        }


def reset_profiling_stats() -> None:
    """Reset all profiling stats (for testing)."""
    with _stats_lock:
        _stats.clear()


class ProfilingMiddleware(BaseHTTPMiddleware):
    """Middleware that measures request processing time and logs slow requests."""

    async def dispatch(self, request: Request, call_next) -> Response:
        start = time.perf_counter()
        response = await call_next(request)
        elapsed_ms = (time.perf_counter() - start) * 1000

        # Add timing header
        response.headers["X-Process-Time"] = f"{elapsed_ms:.2f}ms"

        # Normalize path (strip query params and IDs for grouping)
        path = str(request.url.path)
        # Group parameterized paths: /api/v1/strategies/123/backtest → /api/v1/strategies/*/backtest
        parts = path.strip("/").split("/")
        normalized_parts = []
        for i, part in enumerate(parts):
            if part.isdigit():
                normalized_parts.append("*")
            else:
                normalized_parts.append(part)
        normalized_path = "/" + "/".join(normalized_parts)

        # Update stats
        with _stats_lock:
            bucket = _stats[normalized_path]
            bucket["count"] += 1
            bucket["total_ms"] += elapsed_ms
            bucket["max_ms"] = max(bucket["max_ms"], elapsed_ms)
            bucket["min_ms"] = min(bucket["min_ms"], elapsed_ms)
            if elapsed_ms > _slow_threshold_ms:
                bucket["slow_count"] += 1

        # Log slow requests
        if elapsed_ms > _slow_threshold_ms:
            logger.warning(
                "SLOW REQUEST: %s %s took %.1fms (threshold: %.0fms)",
                request.method,
                path,
                elapsed_ms,
                _slow_threshold_ms,
            )

        return response