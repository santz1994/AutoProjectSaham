"""Simple Prometheus metrics server helper.

Call `start_metrics_server(port)` to start an HTTP endpoint that exposes
Prometheus metrics if `prometheus_client` is installed. This module is a
lightweight convenience wrapper and does nothing when the dependency is
absent.
"""
from __future__ import annotations


def start_metrics_server(port: int = 8000, host: str = '0.0.0.0') -> bool:
    try:
        from prometheus_client import start_http_server

        start_http_server(port, addr=host)
        return True
    except Exception:
        return False


if __name__ == '__main__':
    ok = start_metrics_server(8000)
    if ok:
        print('Prometheus metrics server started on :8000')
    else:
        print('prometheus_client not installed; metrics server not started')
