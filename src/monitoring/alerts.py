"""Alert callback factory that integrates with `ExecutionManager`.

Produces a callable suitable for passing as `alert_callback` to
`ExecutionManager`. The callback records Prometheus metrics and will
optionally push metrics to a Pushgateway if configured.
"""
from __future__ import annotations

import logging
from typing import Callable, Dict

from src.monitoring.metrics import (
    record_order_filled,
    record_order_rejected,
    start_metrics_server,
    push_to_gateway_if_configured,
)
from src.monitoring.notifications import notify_event
from src.monitoring.alert_channels import notify_with_throttle

log = logging.getLogger('autosaham.alerts')


def make_alert_callback(
    start_metrics: bool = False,
    metrics_port: int = 8000,
    throttle_seconds: int = 60,
    require_ack: bool = False,
) -> Callable[[Dict], None]:
    """Return a callback function to handle execution events.

    Usage:
        cb = make_alert_callback(start_metrics=True)
        em = ExecutionManager(..., alert_callback=cb)
    """
    if start_metrics:
        start_metrics_server(metrics_port)

    def _cb(ev: Dict) -> None:
        try:
            etype = ev.get('type')
            if etype == 'order_filled':
                trade = ev.get('trade', {})
                symbol = trade.get('symbol', 'UNKNOWN')
                record_order_filled(symbol)
                # update balance when trade filled if provided
                # ExecutionManager will call set_account_balance externally as appropriate
            elif etype == 'order_rejected':
                symbol = ev.get('symbol', 'UNKNOWN')
                record_order_rejected(symbol)
            elif etype == 'daily_loss_freeze':
                log.warning('daily loss freeze: %s', ev.get('reason'))
            # send optional notifications (Slack/email) with throttling + ack
            try:
                notify_with_throttle(ev, cooldown_seconds=throttle_seconds, require_ack=require_ack)
            except Exception:
                log.exception('notify_with_throttle failed')
            # also call existing notify_event (best-effort)
            try:
                notify_event(ev)
            except Exception:
                log.exception('notify_event failed')
            # try pushgateway
            try:
                push_to_gateway_if_configured()
            except Exception:
                pass
        except Exception:
            log.exception('alert handler failure')

    return _cb
