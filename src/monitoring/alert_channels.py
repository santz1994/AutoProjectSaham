"""Production-ready alert channels with throttling and ack support.

Provides a throttler (to avoid alert floods), ack persistence, and
templated Slack/email sending using the existing notifications helpers.
"""
from __future__ import annotations

import json
import logging
import os
import time
import uuid
from typing import Dict, Optional

from src.monitoring.notifications import send_email_alert, send_slack_alert

LOG = logging.getLogger("autosaham.alert_channels")

_DATA_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data"))
os.makedirs(_DATA_DIR, exist_ok=True)

_THROTTLE_FILE = os.path.join(_DATA_DIR, "alert_throttle.json")
_ACK_FILE = os.path.join(_DATA_DIR, "alert_acks.json")


def _load_json(path: str) -> Dict:
    try:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as fh:
                return json.load(fh)
    except Exception:
        LOG.exception("failed to load %s", path)
    return {}


def _save_json(path: str, data: Dict) -> None:
    try:
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2)
    except Exception:
        LOG.exception("failed to save %s", path)


class AlertThrottler:
    """Simple persistent throttler keyed by string.

    Keeps last-sent timestamps in `_THROTTLE_FILE` so alerts survive restarts.
    """

    def __init__(self, storage_path: Optional[str] = None):
        self.path = storage_path or _THROTTLE_FILE
        self._data = _load_json(self.path)

    def should_send(self, key: str, cooldown_seconds: int) -> bool:
        now = time.time()
        last = float(self._data.get(key) or 0)
        if now - last >= float(cooldown_seconds):
            self._data[key] = now
            _save_json(self.path, self._data)
            return True
        return False


class AckStore:
    """Store ack tokens and their timestamps.

    Simple persistent store backed by `_ACK_FILE`.
    """

    def __init__(self, storage_path: Optional[str] = None):
        self.path = storage_path or _ACK_FILE
        self._data = _load_json(self.path)

    def create_ack(self, ev: Dict) -> str:
        token = str(uuid.uuid4())
        self._data[token] = {"time": time.time(), "event": ev}
        _save_json(self.path, self._data)
        return token

    def ack(self, token: str) -> bool:
        if token in self._data:
            self._data[token]["acked_at"] = time.time()
            _save_json(self.path, self._data)
            return True
        return False

    def list_unacked(self) -> Dict:
        return {t: v for t, v in self._data.items() if "acked_at" not in v}


_THROTTLER = AlertThrottler()
_ACKSTORE = AckStore()


def format_message(
    ev: Dict, include_ack: bool = False, ack_token: Optional[str] = None
) -> str:
    lines = []
    et = ev.get("type") or ev.get("event") or "alert"
    lines.append(f"*AutoSaham {et}*")
    for k, v in ev.items():
        lines.append(f"{k}: {v}")
    if include_ack:
        if not ack_token:
            ack_token = _ACKSTORE.create_ack(ev)
        lines.append("Ack token: " + ack_token)
        lines.append(
            "To ack this alert run: `python -m src.monitoring.alert_channels ack "
            + ack_token
            + "`"
        )
    return "\n".join(lines)


def notify_with_throttle(
    ev: Dict,
    cooldown_seconds: int = 60,
    require_ack: bool = False,
    slack_webhook: Optional[str] = None,
    email_to: Optional[str] = None,
) -> bool:
    """Send the event to Slack/email while respecting throttling and optional ack.

    Returns True if the message was sent (or simulated), False otherwise.
    """
    try:
        key = ev.get("type", "event") + "::" + str(ev.get("symbol", "ALL"))
        if not _THROTTLER.should_send(key, cooldown_seconds):
            LOG.info("throttle suppressed alert for %s", key)
            return False

        ack_token = None
        if require_ack:
            ack_token = _ACKSTORE.create_ack(ev)

        msg = format_message(ev, include_ack=require_ack, ack_token=ack_token)

        sent = False
        # try slack
        try:
            sent = send_slack_alert(msg, webhook_url=slack_webhook) or sent
        except Exception:
            LOG.exception("slack send failed")

        # try email
        try:
            subject = f"AutoSaham alert: {ev.get('type', 'alert')}"
            body = msg
            if email_to:
                sent = send_email_alert(subject, body, to=email_to) or sent
            else:
                sent = send_email_alert(subject, body) or sent
        except Exception:
            LOG.exception("email send failed")

        return bool(sent)
    except Exception:
        LOG.exception("notify_with_throttle failed")
        return False


def ack(token: str) -> bool:
    return _ACKSTORE.ack(token)


if __name__ == "__main__":
    import argparse

    p = argparse.ArgumentParser()
    p.add_argument("cmd", choices=["list-unacked", "ack"])
    p.add_argument("arg", nargs="?")
    args = p.parse_args()
    if args.cmd == "list-unacked":
        print(json.dumps(_ACKSTORE.list_unacked(), indent=2))
    elif args.cmd == "ack":
        tok = args.arg
        if not tok:
            print("token required")
        else:
            ok = ack(tok)
            print("acked" if ok else "not found")
