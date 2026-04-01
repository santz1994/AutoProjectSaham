"""
Slack Notification Integration
================================

Sends trading alerts and notifications to Slack channels.
Integrates with Prometheus AlertManager webhooks.

Timezone: Jakarta (WIB: UTC+7)
Currency: IDR
"""

import asyncio
import json
import logging
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional

import aiohttp

from src.data.idx_api_client import get_jakarta_now, JAKARTA_TZ


logger = logging.getLogger(__name__)


class AlertSeverity(Enum):
    """Alert severity levels."""
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class SlackNotifier:
    """Sends notifications to Slack."""
    
    SEVERITY_COLORS = {
        AlertSeverity.INFO: "#36a64f",
        AlertSeverity.WARNING: "#ff9900",
        AlertSeverity.CRITICAL: "#ff0000",
    }
    
    def __init__(self, webhook_url: str, channel: Optional[str] = None):
        """Initialize Slack notifier."""
        self.webhook_url = webhook_url
        self.channel = channel
    
    async def send_alert(
        self,
        title: str,
        message: str,
        severity: AlertSeverity = AlertSeverity.WARNING,
        fields: Optional[Dict[str, str]] = None,
    ) -> bool:
        """Send alert to Slack."""
        try:
            payload = {
                "channel": self.channel,
                "attachments": [{
                    "fallback": title,
                    "color": self.SEVERITY_COLORS[severity],
                    "title": title,
                    "text": message,
                    "footer": "AutoSaham Trading System",
                }]
            }
            
            if fields:
                payload["attachments"][0]["fields"] = [
                    {"title": k, "value": v, "short": True}
                    for k, v in fields.items()
                ]
            
            async with aiohttp.ClientSession() as session:
                async with session.post(self.webhook_url, json=payload, timeout=aiohttp.ClientTimeout(total=10)) as response:
                    return response.status == 200
        
        except Exception as e:
            logger.error(f"Slack notification error: {e}")
            return False
    
    async def send_order_notification(
        self,
        symbol: str,
        side: str,
        quantity: int,
        price: float,
        status: str,
    ) -> bool:
        """Send order notification."""
        fields = {
            "Symbol": symbol,
            "Side": side.upper(),
            "Quantity": f"{quantity:,}",
            "Price": f"Rp {price:,.0f}",
            "Status": status,
        }
        return await self.send_alert(
            title=f"Order {status}: {symbol}",
            message=f"{quantity:,} {side} {symbol} @ Rp {price:,.0f}",
            severity=AlertSeverity.INFO,
            fields=fields,
        )
    
    async def send_position_alert(
        self,
        symbol: str,
        quantity: int,
        unrealized_pl: float,
        unrealized_pl_pct: float,
    ) -> bool:
        """Send position alert."""
        severity = (
            AlertSeverity.CRITICAL if unrealized_pl_pct < -5
            else AlertSeverity.WARNING if unrealized_pl_pct < -2
            else AlertSeverity.INFO
        )
        
        fields = {
            "Symbol": symbol,
            "Quantity": f"{quantity:,}",
            "P&L": f"Rp {unrealized_pl:,.0f}",
            "P&L %": f"{unrealized_pl_pct:+.2f}%",
        }
        
        return await self.send_alert(
            title=f"Position: {symbol}",
            message=f"P&L: Rp {unrealized_pl:,.0f} ({unrealized_pl_pct:+.2f}%)",
            severity=severity,
            fields=fields,
        )


if __name__ == "__main__":
    print("Slack notifications module ready")
