"""Prometheus metrics helpers for AutoSaham.

Provides lightweight helpers to expose metrics via an HTTP endpoint and
record key events (orders filled/rejected, balance). The module keeps
usage simple so it can be used without pushgateway configuration.
"""
from __future__ import annotations

import logging
import os
from prometheus_client import Counter, Gauge, start_http_server

log = logging.getLogger('autosaham.metrics')

# Counters and gauges
orders_filled = Counter('autosaham_orders_filled_total', 'Number of filled orders', ['symbol'])
orders_rejected = Counter('autosaham_orders_rejected_total', 'Number of rejected orders', ['symbol'])
orders_total = Counter('autosaham_orders_total', 'Total orders', ['symbol'])
account_balance = Gauge('autosaham_account_balance', 'Account cash + market value')


def start_metrics_server(port: int = 8000) -> int:
    """Start a background HTTP server exposing /metrics on `port`.

    Returns the port that the server was started on.
    """
    try:
        start_http_server(port)
        log.info('metrics HTTP server started on port %d', port)
    except Exception:
        log.exception('failed to start metrics server')
    return int(port)


def record_order_filled(symbol: str) -> None:
    try:
        orders_filled.labels(symbol=symbol).inc()
        orders_total.labels(symbol=symbol).inc()
    except Exception:
        log.exception('failed to record order_filled')


def record_order_rejected(symbol: str) -> None:
    try:
        orders_rejected.labels(symbol=symbol).inc()
        orders_total.labels(symbol=symbol).inc()
    except Exception:
        log.exception('failed to record order_rejected')


def set_account_balance(value: float) -> None:
    try:
        account_balance.set(float(value))
    except Exception:
        log.exception('failed to set account_balance')


def push_to_gateway_if_configured(job: str = 'autosaham') -> bool:
    """Attempt to push metrics to a configured Pushgateway (optional).

    Reads `PROMETHEUS_PUSHGATEWAY` from environment or .env via `python-dotenv`.
    Returns True on success, False otherwise.
    """
    try:
        from src.utils.secrets import get_secret
        gateway = get_secret('PROMETHEUS_PUSHGATEWAY')
        if not gateway:
            return False
        # push_to_gateway may require a registry in some versions; attempt best-effort
        try:
            from prometheus_client import push_to_gateway
            push_to_gateway(gateway, job=job)
            log.info('pushed metrics to %s', gateway)
            return True
        except Exception:
            log.exception('failed to push metrics to gateway')
            return False
    except Exception:
        log.exception('push_to_gateway_if_configured failed')
        return False
