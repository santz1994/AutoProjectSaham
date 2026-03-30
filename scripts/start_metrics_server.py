"""Helper script to start the metrics HTTP server used by monitoring.

This script is intentionally minimal: it starts the prometheus HTTP server
and blocks so it can be used via the GUI start button or directly.
"""
from __future__ import annotations

from src.monitoring.metrics import start_metrics_server


def main():
    port = 8000
    start_metrics_server(port)
    print('Metrics server started on port', port)
    # block forever
    try:
        import time
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        print('Metrics server stopped')


if __name__ == '__main__':
    main()
