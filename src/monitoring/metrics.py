"""Lightweight Prometheus metrics helpers for AutoSaham.

If `prometheus_client` is installed this module exposes helpers to record
ETL metrics and to render the `/metrics` output. When the dependency is
missing the functions are safe no-ops (or raise when rendering metrics).
"""
from __future__ import annotations

try:
    from prometheus_client import (
        CONTENT_TYPE_LATEST,
        CollectorRegistry,
        Counter,
        Histogram,
        generate_latest,
    )

    PROM_AVAILABLE = True
except Exception:
    PROM_AVAILABLE = False


if PROM_AVAILABLE:
    registry = CollectorRegistry()

    etl_runs_total = Counter(
        "autosaham_etl_runs_total",
        "Total ETL runs",
        registry=registry,
    )

    etl_runs_success = Counter(
        "autosaham_etl_runs_success_total",
        "Successful ETL runs",
        registry=registry,
    )

    etl_runs_failure = Counter(
        "autosaham_etl_runs_failure_total",
        "Failed ETL runs",
        registry=registry,
    )

    etl_duration_seconds = Histogram(
        "autosaham_etl_duration_seconds",
        "ETL run duration in seconds",
        registry=registry,
    )

    def record_etl_run(
        duration_seconds: float | None = None, success: bool = True
    ) -> None:
        etl_runs_total.inc()
        if success:
            etl_runs_success.inc()
        else:
            etl_runs_failure.inc()
            if duration_seconds is not None:
                etl_duration_seconds.observe(float(duration_seconds))

    def metrics_text() -> tuple[bytes, str]:
        """Return the latest metrics payload and content type."""
        return generate_latest(registry), CONTENT_TYPE_LATEST

else:

    def record_etl_run(
        duration_seconds: float | None = None, success: bool = True
    ) -> None:
        # no-op when prometheus_client is unavailable
        return

    def metrics_text() -> tuple[bytes, str]:
        raise RuntimeError("prometheus_client is not installed")


__all__ = ["PROM_AVAILABLE", "record_etl_run", "metrics_text"]
