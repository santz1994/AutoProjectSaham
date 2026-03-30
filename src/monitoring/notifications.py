"""Notification helpers (Slack webhook + email) for alerts.

Designed to be lightweight and optional: if no webhook or SMTP is
configured the functions will return False but not raise.
"""
from __future__ import annotations

import logging
import smtplib
from email.message import EmailMessage
from typing import Optional

import requests

from src.utils.secrets import get_secret

log = logging.getLogger('autosaham.notifications')


def send_slack_alert(text: str, webhook_url: Optional[str] = None) -> bool:
    webhook = webhook_url or get_secret('SLACK_WEBHOOK_URL')
    if not webhook:
        return False
    try:
        payload = {'text': text}
        r = requests.post(webhook, json=payload, timeout=5)
        r.raise_for_status()
        return True
    except Exception:
        log.exception('failed to send slack alert')
        return False


def send_email_alert(subject: str, body: str, to: Optional[str] = None) -> bool:
    to_addr = to or get_secret('ALERT_EMAIL_TO')
    if not to_addr:
        return False
    host = get_secret('SMTP_HOST')
    port = int(get_secret('SMTP_PORT') or 587)
    user = get_secret('SMTP_USER')
    pwd = get_secret('SMTP_PASS')
    if not host:
        return False
    try:
        msg = EmailMessage()
        msg['Subject'] = subject
        msg['From'] = user or f'no-reply@{host}'
        msg['To'] = to_addr
        msg.set_content(body)

        with smtplib.SMTP(host, port, timeout=10) as s:
            s.starttls()
            if user and pwd:
                s.login(user, pwd)
            s.send_message(msg)
        return True
    except Exception:
        log.exception('failed to send email alert')
        return False


def notify_event(ev: dict) -> None:
    """Send a short notification for the event to configured channels."""
    try:
        etype = ev.get('type', 'event')
        # craft a concise message
        subject = f'AutoSaham alert: {etype}'
        body_lines = [f'{k}: {v}' for k, v in ev.items()]
        body = '\n'.join(body_lines)
        # best-effort: Slack then email
        try:
            send_slack_alert(f'*{subject}*\n{body}')
        except Exception:
            pass
        try:
            send_email_alert(subject, body)
        except Exception:
            pass
    except Exception:
        log.exception('notify_event failed')
