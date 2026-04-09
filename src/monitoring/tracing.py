"""OpenTelemetry tracing bootstrap helpers for AutoSaham.

Tracing is optional and activated through environment flags so local
development can run without OpenTelemetry dependencies.
"""
from __future__ import annotations

import os
import threading
from typing import Any, Optional

_LOCK = threading.RLock()
_TRACE_READY = False
_TRACER: Optional[Any] = None


def _env_flag(name: str, default: bool = False) -> bool:
    raw = str(os.getenv(name, "")).strip().lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "on"}


def init_tracing(service_name: str = "autosaham-api") -> bool:
    """Initialize OpenTelemetry tracer provider when enabled by env."""
    global _TRACE_READY
    global _TRACER

    if _TRACE_READY:
        return True

    if not _env_flag("AUTOSAHAM_TRACING_ENABLED", False):
        return False

    with _LOCK:
        if _TRACE_READY:
            return True

        try:
            from opentelemetry import trace
            from opentelemetry.sdk.resources import Resource
            from opentelemetry.sdk.trace import TracerProvider
            from opentelemetry.sdk.trace.export import (
                BatchSpanProcessor,
                ConsoleSpanExporter,
            )

            safe_service_name = str(service_name or "autosaham-api").strip() or "autosaham-api"
            resource = Resource.create({"service.name": safe_service_name})
            provider = TracerProvider(resource=resource)

            otlp_endpoint = str(os.getenv("AUTOSAHAM_OTLP_HTTP_ENDPOINT", "")).strip()
            if otlp_endpoint:
                from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
                    OTLPSpanExporter,
                )

                timeout_seconds = max(
                    1.0,
                    float(os.getenv("AUTOSAHAM_OTLP_TIMEOUT_SECONDS", "5") or 5),
                )
                exporter = OTLPSpanExporter(
                    endpoint=otlp_endpoint,
                    timeout=timeout_seconds,
                )
            else:
                exporter = ConsoleSpanExporter()

            provider.add_span_processor(BatchSpanProcessor(exporter))
            trace.set_tracer_provider(provider)
            _TRACER = trace.get_tracer("autosaham.api")
            _TRACE_READY = True
            return True
        except Exception:
            _TRACE_READY = False
            _TRACER = None
            return False


def get_tracer() -> Optional[Any]:
    return _TRACER


def reset_tracing_for_tests() -> None:
    """Reset module-level tracing state for deterministic unit tests."""
    global _TRACE_READY
    global _TRACER

    with _LOCK:
        _TRACE_READY = False
        _TRACER = None


__all__ = [
    "init_tracing",
    "get_tracer",
    "reset_tracing_for_tests",
]
