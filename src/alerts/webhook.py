"""Webhook alert sender with retries and exponential backoff.

Provides a small helper to POST JSON payloads to an alert
webhook endpoint. If `requests` is not available the function
logs a warning and returns False.
"""
from __future__ import annotations

import logging
import random
import time
from typing import Any, Dict

try:
    import requests  # type: ignore
    REQUESTS_AVAILABLE = True
except Exception:
    REQUESTS_AVAILABLE = False

log = logging.getLogger("autosaham.alerts")


def send_alert_webhook(
    url: str,
    payload: Dict[str, Any],
    timeout: float = 5.0,
    retries: int = 3,
    backoff: float = 0.5,
    jitter: float = 0.0,
) -> bool:
    """POST `payload` as JSON to `url` with retries.

    Returns True if a 2xx response is received, False otherwise.
    This function is best-effort and will not raise on network
    errors (it returns False instead).
    """
    if not REQUESTS_AVAILABLE:
        log.warning("requests not available; cannot send webhook to %s", url)
        return False

    headers = {"Content-Type": "application/json"}

    last_exc = None
    for attempt in range(1, max(1, retries) + 1):
        try:
            resp = requests.post(
                url,
                json=payload,
                timeout=timeout,
                headers=headers,
            )
            status = getattr(resp, "status_code", 0)
            if 200 <= status < 300:
                return True
            log.warning(
                "webhook %s returned status %s (attempt %d)",
                url,
                status,
                attempt,
            )
        except Exception as e:  # pragma: no cover - network error branch
            last_exc = e
            log.exception(
                "webhook send failed (attempt %d) for %s", attempt, url
            )

        # backoff before next attempt
        if attempt < retries:
            sleep_for = backoff * (2 ** (attempt - 1)) + random.uniform(0, jitter)
            try:
                time.sleep(float(sleep_for))
            except Exception:
                pass

    if last_exc:
        log.debug("webhook final error: %s", last_exc)
    return False


__all__ = ["send_alert_webhook"]
