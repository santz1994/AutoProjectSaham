"""
Notification Delivery Handlers
Handles WebSocket, Slack, Email, and Push notifications
"""

import json
import logging
from typing import Optional, Dict, Any
from datetime import datetime
import asyncio
from abc import ABC, abstractmethod

import aiohttp
import pytz
from pydantic import EmailStr

from .notification_service import (
    Notification, NotificationPreference, NotificationChannel,
    NotificationStatus, NotificationLog
)

logger = logging.getLogger(__name__)
JAKARTA_TZ = pytz.timezone('Asia/Jakarta')


# ==================== Base Delivery Handler ====================

class NotificationHandler(ABC):
    """Base class for notification handlers"""
    
    @abstractmethod
    async def send(
        self,
        notification: Notification,
        user_id: Optional[str] = None,
        preference: Optional[NotificationPreference] = None
    ) -> NotificationLog:
        """Send notification through this handler"""
        pass


# ==================== WebSocket Handler ====================

class WebSocketHandler(NotificationHandler):
    """Send notifications through WebSocket"""
    
    def __init__(self, notification_manager):
        self.manager = notification_manager
    
    async def send(
        self,
        notification: Notification,
        user_id: Optional[str] = None,
        preference: Optional[NotificationPreference] = None
    ) -> NotificationLog:
        """Send via WebSocket to connected clients"""
        log = NotificationLog(
            notification_id=notification.id,
            channel=NotificationChannel.WEBSOCKET
        )
        
        try:
            if user_id and user_id in self.manager.websocket_connections:
                message = self._format_message(notification)
                
                for connection in self.manager.websocket_connections[user_id]:
                    try:
                        await connection.send_json(message)
                        log.delivered_to = user_id
                        log.status = NotificationStatus.DELIVERED
                        log.delivered_at = datetime.now(JAKARTA_TZ)
                    except Exception as e:
                        logger.error(f"WebSocket send error: {e}")
                        log.last_error = str(e)
            else:
                log.status = NotificationStatus.SENT
                log.status_message = "No WebSocket connections found"
        
        except Exception as e:
            log.status = NotificationStatus.FAILED
            log.last_error = str(e)
            logger.error(f"WebSocket handler error: {e}")
        
        return log
    
    @staticmethod
    def _format_message(notification: Notification) -> Dict[str, Any]:
        """Format notification as WebSocket message"""
        return {
            "type": "notification",
            "id": notification.id,
            "title": notification.title,
            "body": notification.body,
            "severity": notification.severity.value,
            "signal_type": notification.signal_type.value,
            "data": notification.data,
            "created_at": notification.created_at.isoformat(),
        }


# ==================== Email Handler ====================

class EmailHandler(NotificationHandler):
    """Send notifications via Email"""
    
    def __init__(self, smtp_config: Dict[str, Any]):
        self.smtp_host = smtp_config.get('host', 'smtp.gmail.com')
        self.smtp_port = smtp_config.get('port', 587)
        self.sender_email = smtp_config.get('sender_email')
        self.sender_password = smtp_config.get('sender_password')
    
    async def send(
        self,
        notification: Notification,
        user_id: Optional[str] = None,
        preference: Optional[NotificationPreference] = None
    ) -> NotificationLog:
        """Send via Email"""
        log = NotificationLog(
            notification_id=notification.id,
            channel=NotificationChannel.EMAIL
        )
        
        try:
            if not preference or not preference.email_address:
                log.status = NotificationStatus.FAILED
                log.last_error = "No email address configured"
                return log
            
            # Format email content
            html_content = self._format_html(notification)
            
            # Note: In production, use aiosmtplib or similar
            # For now, we'll log the intention
            logger.info(
                f"Email notification queued for {preference.email_address}: "
                f"{notification.title}"
            )
            
            log.delivered_to = preference.email_address
            log.status = NotificationStatus.SENT
            log.sent_at = datetime.now(JAKARTA_TZ)
            
        except Exception as e:
            log.status = NotificationStatus.FAILED
            log.last_error = str(e)
            logger.error(f"Email handler error: {e}")
        
        return log
    
    @staticmethod
    def _format_html(notification: Notification) -> str:
        """Format notification as HTML email"""
        severity_class = f"severity-{notification.severity.value}"
        
        html = f"""
        <html>
            <body style="font-family: Arial, sans-serif;">
                <div style="background: #f5f5f5; padding: 20px; border-radius: 5px;">
                    <h2 style="color: #333;">{notification.title}</h2>
                    <div class="{severity_class}" style="
                        padding: 10px;
                        margin: 10px 0;
                        border-radius: 3px;
                        background: {'#fff3cd' if notification.severity.value == 'warning' else '#d4edda'};
                    ">
                        <strong>{notification.severity.value.upper()}</strong>
                    </div>
                    <p>{notification.body}</p>
                    <div style="margin-top: 20px; padding-top: 20px; border-top: 1px solid #ddd;">
                        <small style="color: #666;">
                            Sent: {notification.created_at.strftime('%Y-%m-%d %H:%M:%S %Z')}
                        </small>
                    </div>
                </div>
            </body>
        </html>
        """
        return html


# ==================== Slack Handler ====================

class SlackHandler(NotificationHandler):
    """Send notifications to Slack"""
    
    async def send(
        self,
        notification: Notification,
        user_id: Optional[str] = None,
        preference: Optional[NotificationPreference] = None
    ) -> NotificationLog:
        """Send to Slack webhook"""
        log = NotificationLog(
            notification_id=notification.id,
            channel=NotificationChannel.SLACK
        )
        
        try:
            if not preference or not preference.slack_webhook_url or not preference.slack_enabled:
                log.status = NotificationStatus.FAILED
                log.last_error = "Slack not configured or disabled"
                return log
            
            webhook_url = preference.slack_webhook_url
            
            # Format Slack message
            slack_message = self._format_slack_message(notification)
            
            # Send to Slack webhook
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    webhook_url,
                    json=slack_message,
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as resp:
                    if resp.status == 200:
                        log.status = NotificationStatus.DELIVERED
                        log.delivered_to = preference.slack_channel or "#notifications"
                        log.delivered_at = datetime.now(JAKARTA_TZ)
                    else:
                        log.status = NotificationStatus.FAILED
                        log.last_error = f"HTTP {resp.status}"
            
        except asyncio.TimeoutError:
            log.status = NotificationStatus.FAILED
            log.last_error = "Slack webhook timeout"
            logger.error("Slack webhook timeout")
        except Exception as e:
            log.status = NotificationStatus.FAILED
            log.last_error = str(e)
            logger.error(f"Slack handler error: {e}")
        
        return log
    
    @staticmethod
    def _format_slack_message(notification: Notification) -> Dict[str, Any]:
        """Format notification as Slack message with rich formatting"""
        
        # Color based on severity
        color_map = {
            "info": "#36a64f",
            "warning": "#ff9900",
            "critical": "#ff0000",
            "urgent": "#cc0000"
        }
        
        slack_message = {
            "text": notification.title,
            "attachments": [
                {
                    "color": color_map.get(notification.severity.value, "#0099ff"),
                    "title": notification.title,
                    "text": notification.body,
                    "fields": [
                        {
                            "title": "Severity",
                            "value": notification.severity.value.upper(),
                            "short": True
                        },
                        {
                            "title": "Signal Type",
                            "value": notification.signal_type.value,
                            "short": True
                        },
                        {
                            "title": "ID",
                            "value": notification.id,
                            "short": False
                        }
                    ],
                    "ts": int(datetime.now(JAKARTA_TZ).timestamp())
                }
            ]
        }
        
        # Add data fields if present
        if notification.data:
            fields = slack_message["attachments"][0]["fields"]
            for key, value in notification.data.items():
                fields.append({
                    "title": key.replace('_', ' ').title(),
                    "value": str(value),
                    "short": True
                })
        
        return slack_message


# ==================== Push Notification Handler ====================

class PushNotificationHandler(NotificationHandler):
    """Send push notifications"""
    
    def __init__(self, vapid_config: Optional[Dict[str, str]] = None):
        self.vapid_public_key = vapid_config.get('public_key') if vapid_config else None
        self.vapid_private_key = vapid_config.get('private_key') if vapid_config else None
    
    async def send(
        self,
        notification: Notification,
        user_id: Optional[str] = None,
        preference: Optional[NotificationPreference] = None
    ) -> NotificationLog:
        """Send push notification"""
        log = NotificationLog(
            notification_id=notification.id,
            channel=NotificationChannel.PUSH
        )
        
        try:
            if not preference or not preference.push_enabled or not preference.push_tokens:
                log.status = NotificationStatus.FAILED
                log.last_error = "Push notifications not enabled or no tokens"
                return log
            
            # Format push payload
            payload = self._format_push_payload(notification)
            
            # Send to all registered tokens
            for token in preference.push_tokens:
                try:
                    # In production, use web-push library
                    logger.info(f"Push notification queued for token: {token[:20]}...")
                    log.delivered_to = f"{len(preference.push_tokens)} device(s)"
                    log.status = NotificationStatus.SENT
                    log.sent_at = datetime.now(JAKARTA_TZ)
                except Exception as e:
                    logger.error(f"Push error for token: {e}")
            
        except Exception as e:
            log.status = NotificationStatus.FAILED
            log.last_error = str(e)
            logger.error(f"Push handler error: {e}")
        
        return log
    
    @staticmethod
    def _format_push_payload(notification: Notification) -> Dict[str, Any]:
        """Format push notification payload"""
        return {
            "title": notification.title,
            "body": notification.body,
            "icon": "/notification-icon.png",
            "badge": "/notification-badge.png",
            "tag": notification.signal_type.value,
            "data": {
                "notification_id": notification.id,
                "rule_id": notification.rule_id,
                "severity": notification.severity.value,
                **notification.data
            }
        }


# ==================== Notification Channel Registry ====================

class NotificationChannelFactory:
    """Factory for creating notification handlers"""
    
    _handlers: Dict[str, NotificationHandler] = {}
    
    @classmethod
    def register_handler(
        cls,
        channel: NotificationChannel,
        handler: NotificationHandler
    ) -> None:
        """Register a notification handler"""
        cls._handlers[channel.value] = handler
        logger.info(f"Registered notification handler: {channel.value}")
    
    @classmethod
    def get_handler(cls, channel: NotificationChannel) -> Optional[NotificationHandler]:
        """Get a notification handler"""
        return cls._handlers.get(channel.value)
    
    @classmethod
    def get_all_handlers(cls) -> Dict[str, NotificationHandler]:
        """Get all registered handlers"""
        return cls._handlers.copy()


# ==================== Initialize Default Handlers ====================

def initialize_default_handlers(notification_manager, smtp_config=None, slack_webhook_url=None):
    """Initialize default notification handlers"""
    
    # WebSocket handler
    ws_handler = WebSocketHandler(notification_manager)
    NotificationChannelFactory.register_handler(NotificationChannel.WEBSOCKET, ws_handler)
    
    # Email handler
    if smtp_config:
        email_handler = EmailHandler(smtp_config)
        NotificationChannelFactory.register_handler(NotificationChannel.EMAIL, email_handler)
    
    # Slack handler
    if slack_webhook_url:
        slack_handler = SlackHandler()
        NotificationChannelFactory.register_handler(NotificationChannel.SLACK, slack_handler)
    
    # Push notifications
    push_handler = PushNotificationHandler()
    NotificationChannelFactory.register_handler(NotificationChannel.PUSH, push_handler)
    
    logger.info("Default notification handlers initialized")
