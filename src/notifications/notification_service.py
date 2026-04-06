"""
Notification Service - Core notification management system
Supports WebSocket real-time alerts, Slack/email, push notifications
Jakarta timezone aware with BEI trading hours compliance
"""

from enum import Enum
from typing import List, Dict, Any, Optional, Callable
from datetime import datetime, timedelta
from dataclasses import dataclass, asdict, field
import asyncio
import json
import logging
from abc import ABC, abstractmethod
from collections import deque
import uuid

import pytz
from pydantic import BaseModel, Field, validator

logger = logging.getLogger(__name__)

# ==================== Constants & Enums ====================

JAKARTA_TZ = pytz.timezone('Asia/Jakarta')
BEI_START_HOUR = 9
BEI_START_MINUTE = 30
BEI_END_HOUR = 16
BEI_END_MINUTE = 0
BEI_TRADING_DAYS = {0, 1, 2, 3, 4}  # Monday-Friday


class NotificationChannel(str, Enum):
    """Notification delivery channels"""
    WEBSOCKET = "websocket"      # Real-time browser notifications
    PUSH = "push"                 # Browser/mobile push notifications
    EMAIL = "email"               # Email notifications
    SLACK = "slack"               # Slack webhook notifications
    SMS = "sms"                   # SMS notifications (future)
    IN_APP = "in_app"            # In-app notification bell


class AlertSeverity(str, Enum):
    """Alert severity levels"""
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"
    URGENT = "urgent"


class TradeSignalType(str, Enum):
    """Types of trading signals that trigger alerts"""
    BUY_SIGNAL = "buy_signal"
    SELL_SIGNAL = "sell_signal"
    STOP_LOSS = "stop_loss"
    TAKE_PROFIT = "take_profit"
    ANOMALY_DETECTED = "anomaly_detected"
    TREND_CHANGE = "trend_change"
    VOLUME_SPIKE = "volume_spike"
    PRICE_LEVEL = "price_level"
    PORTFOLIO_ALERT = "portfolio_alert"
    RISK_WARNING = "risk_warning"


class NotificationStatus(str, Enum):
    """Notification delivery status"""
    PENDING = "pending"
    SENT = "sent"
    DELIVERED = "delivered"
    FAILED = "failed"
    EXPIRED = "expired"


# ==================== Pydantic Models ====================

class AlertRule(BaseModel):
    """Alert rule configuration"""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str = Field(..., min_length=1, max_length=100)
    symbol: Optional[str] = None  # None = all symbols
    signal_type: TradeSignalType
    severity: AlertSeverity = AlertSeverity.INFO
    enabled: bool = True
    channels: List[NotificationChannel] = Field(default=[NotificationChannel.WEBSOCKET])
    
    # Conditions
    condition: Dict[str, Any] = Field(default={})  # e.g., {"price_change": ">5%"}
    time_window: Optional[int] = Field(None, ge=1, le=1440)  # Minutes, max 24h
    
    # Jakarta timezone scheduling
    active_hours_start: str = "09:30"  # HHmm format
    active_hours_end: str = "16:00"
    active_days: List[int] = Field(default=[0, 1, 2, 3, 4])  # 0=Mon, 4=Fri
    
    # Notification settings
    throttle_seconds: int = Field(default=60, ge=0)  # Minimum seconds between alerts
    retry_count: int = Field(default=3, ge=0)
    retry_interval_seconds: int = Field(default=30, ge=10)
    
    created_at: datetime = Field(default_factory=lambda: datetime.now(JAKARTA_TZ))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(JAKARTA_TZ))
    
    @validator('active_hours_start', 'active_hours_end')
    def validate_time_format(cls, v):
        """Validate HHmm time format"""
        try:
            h, m = int(v[:2]), int(v[2:4])
            if not (0 <= h <= 23 and 0 <= m <= 59):
                raise ValueError("Invalid time")
            return v
        except (ValueError, IndexError):
            raise ValueError("Time must be in HHmm format (e.g., '09:30')")


class NotificationPreference(BaseModel):
    """User notification preferences"""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str
    
    # Channel preferences
    channels_enabled: List[NotificationChannel] = Field(
        default=[NotificationChannel.WEBSOCKET, NotificationChannel.EMAIL]
    )
    
    # Email settings
    email_address: Optional[str] = None
    email_frequency: str = Field(default="immediate")  # immediate, daily, weekly
    email_digest: bool = True
    
    # Slack settings
    slack_webhook_url: Optional[str] = None
    slack_channel: Optional[str] = "#trading-alerts"
    slack_enabled: bool = False
    
    # Push notification settings
    push_enabled: bool = True
    push_tokens: List[str] = Field(default=[])  # Browser/mobile device tokens
    
    # Severity filtering
    min_severity: AlertSeverity = AlertSeverity.INFO
    
    # Time preferences (Jakarta timezone)
    quiet_hours_start: Optional[str] = None  # HHmm format
    quiet_hours_end: Optional[str] = None
    do_not_disturb_enabled: bool = False
    
    # Symbol preferences
    tracked_symbols: List[str] = Field(default=[])  # Empty = all symbols
    excluded_symbols: List[str] = Field(default=[])
    
    # Alert type preferences
    alert_types: List[TradeSignalType] = Field(
        default=[
            TradeSignalType.BUY_SIGNAL,
            TradeSignalType.SELL_SIGNAL,
            TradeSignalType.STOP_LOSS,
            TradeSignalType.ANOMALY_DETECTED
        ]
    )
    
    created_at: datetime = Field(default_factory=lambda: datetime.now(JAKARTA_TZ))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(JAKARTA_TZ))


class Notification(BaseModel):
    """Single notification message"""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    rule_id: str
    user_id: Optional[str] = None  # None = broadcast
    
    title: str = Field(..., min_length=1, max_length=200)
    body: str = Field(..., min_length=1, max_length=2000)
    data: Dict[str, Any] = Field(default={})  # Extra context: symbol, price, etc.
    
    signal_type: TradeSignalType
    severity: AlertSeverity = AlertSeverity.INFO
    
    channels: List[NotificationChannel]
    status: NotificationStatus = NotificationStatus.PENDING
    
    created_at: datetime = Field(default_factory=lambda: datetime.now(JAKARTA_TZ))
    sent_at: Optional[datetime] = None
    delivered_at: Optional[datetime] = None
    expired_at: Optional[datetime] = None
    
    retry_count: int = Field(default=0, ge=0)
    last_error: Optional[str] = None
    
    # Tracking
    read: bool = False
    read_at: Optional[datetime] = None
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class NotificationLog(BaseModel):
    """Log entry for notification delivery"""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    notification_id: str
    channel: NotificationChannel
    status: NotificationStatus = NotificationStatus.PENDING
    
    delivered_to: Optional[str] = None  # Email, Slack channel, etc.
    status_message: Optional[str] = None
    
    sent_at: datetime = Field(default_factory=lambda: datetime.now(JAKARTA_TZ))
    delivered_at: Optional[datetime] = None
    
    retry_count: int = Field(default=0, ge=0)
    last_error: Optional[str] = None


# ==================== Notification Manager ====================

class NotificationManager:
    """Core notification management and routing"""
    
    def __init__(self, max_queue_size: int = 1000):
        self.notification_queue: deque = deque(maxlen=max_queue_size)
        self.delivery_handlers: Dict[NotificationChannel, Callable] = {}
        self.websocket_connections: Dict[str, List] = {}  # user_id -> connections
        self.alert_rules: Dict[str, AlertRule] = {}
        self.user_preferences: Dict[str, NotificationPreference] = {}
        self.notification_logs: List[NotificationLog] = []
        self.last_alerttime: Dict[str, datetime] = {}  # throttling
        
    def register_handler(
        self,
        channel: NotificationChannel,
        handler: Callable
    ) -> None:
        """Register a notification delivery handler"""
        self.delivery_handlers[channel] = handler
        logger.info(f"Registered handler for channel: {channel.value}")
    
    def add_alert_rule(self, rule: AlertRule) -> str:
        """Add an alert rule"""
        self.alert_rules[rule.id] = rule
        logger.info(f"Added alert rule: {rule.name} (ID: {rule.id})")
        return rule.id
    
    def update_alert_rule(self, rule_id: str, updates: Dict[str, Any]) -> AlertRule:
        """Update an alert rule"""
        if rule_id not in self.alert_rules:
            raise ValueError(f"Alert rule not found: {rule_id}")
        
        rule = self.alert_rules[rule_id]
        for key, value in updates.items():
            if hasattr(rule, key):
                setattr(rule, key, value)
        
        rule.updated_at = datetime.now(JAKARTA_TZ)
        logger.info(f"Updated alert rule: {rule_id}")
        return rule
    
    def delete_alert_rule(self, rule_id: str) -> bool:
        """Delete an alert rule (soft delete by disabling)"""
        if rule_id not in self.alert_rules:
            raise ValueError(f"Alert rule not found: {rule_id}")
        
        self.alert_rules[rule_id].enabled = False
        logger.info(f"Disabled alert rule: {rule_id}")
        return True
    
    def set_user_preference(self, preference: NotificationPreference) -> str:
        """Set user notification preferences"""
        self.user_preferences[preference.user_id] = preference
        logger.info(f"Set preferences for user: {preference.user_id}")
        return preference.id
    
    def get_user_preference(self, user_id: str) -> Optional[NotificationPreference]:
        """Get user notification preferences"""
        return self.user_preferences.get(user_id)
    
    def is_inside_bei_hours(self, dt: Optional[datetime] = None) -> bool:
        """Check if datetime is inside BEI trading hours"""
        if dt is None:
            dt = datetime.now(JAKARTA_TZ)
        
        # Check day of week (0=Monday, 4=Friday)
        if dt.weekday() not in BEI_TRADING_DAYS:
            return False
        
        # Check time
        time_minutes = dt.hour * 60 + dt.minute
        start_minutes = BEI_START_HOUR * 60 + BEI_START_MINUTE
        end_minutes = BEI_END_HOUR * 60 + BEI_END_MINUTE
        
        return start_minutes <= time_minutes <= end_minutes
    
    def is_inside_active_hours(self, rule: AlertRule, dt: Optional[datetime] = None) -> bool:
        """Check if datetime is inside rule's active hours"""
        if dt is None:
            dt = datetime.now(JAKARTA_TZ)
        
        # Check day of week
        if dt.weekday() not in rule.active_days:
            return False
        
        # Parse time
        try:
            start_h, start_m = int(rule.active_hours_start[:2]), int(rule.active_hours_start[2:4])
            end_h, end_m = int(rule.active_hours_end[:2]), int(rule.active_hours_end[2:4])
        except (ValueError, IndexError):
            return True  # Invalid format, allow all times
        
        # Check time
        time_minutes = dt.hour * 60 + dt.minute
        start_minutes = start_h * 60 + start_m
        end_minutes = end_h * 60 + end_m
        
        return start_minutes <= time_minutes <= end_minutes
    
    def should_throttle(self, rule_id: str) -> bool:
        """Check if notification should be throttled"""
        if rule_id not in self.last_alerttime:
            return False
        
        rule = self.alert_rules[rule_id]
        last_time = self.last_alerttime[rule_id]
        elapsed = (datetime.now(JAKARTA_TZ) - last_time).total_seconds()
        
        return elapsed < rule.throttle_seconds
    
    def record_alert_sent(self, rule_id: str) -> None:
        """Record when an alert was sent for throttling"""
        self.last_alerttime[rule_id] = datetime.now(JAKARTA_TZ)
    
    async def send_notification(
        self,
        notification: Notification,
        user_id: Optional[str] = None
    ) -> None:
        """Send notification through configured channels"""
        notification.sent_at = datetime.now(JAKARTA_TZ)
        self.notification_queue.append(notification)
        
        # Get user preference
        pref = None
        if user_id:
            pref = self.get_user_preference(user_id)
        
        # Filter channels based on preference
        channels = notification.channels
        if pref:
            channels = [c for c in channels if c in pref.channels_enabled]
            
            # Check quiet hours
            if pref.do_not_disturb_enabled:
                if self._in_quiet_hours(pref):
                    logger.info(f"User {user_id} in quiet hours, queueing for delivery")
        
        # Send through each channel
        for channel in channels:
            if channel in self.delivery_handlers:
                try:
                    await self.delivery_handlers[channel](notification, user_id, pref)
                    notification.status = NotificationStatus.SENT
                except Exception as e:
                    notification.status = NotificationStatus.FAILED
                    notification.last_error = str(e)
                    logger.error(f"Failed to send notification via {channel.value}: {e}")
    
    def _in_quiet_hours(self, pref: NotificationPreference) -> bool:
        """Check if current time is in user's quiet hours"""
        if not pref.quiet_hours_start or not pref.quiet_hours_end:
            return False
        
        dt = datetime.now(JAKARTA_TZ)
        try:
            start_h, start_m = int(pref.quiet_hours_start[:2]), int(pref.quiet_hours_start[2:4])
            end_h, end_m = int(pref.quiet_hours_end[:2]), int(pref.quiet_hours_end[2:4])
        except (ValueError, IndexError):
            return False
        
        time_minutes = dt.hour * 60 + dt.minute
        start_minutes = start_h * 60 + start_m
        end_minutes = end_h * 60 + end_m
        
        if start_minutes <= end_minutes:
            return start_minutes <= time_minutes <= end_minutes
        else:  # Spans midnight
            return time_minutes >= start_minutes or time_minutes <= end_minutes
    
    def register_websocket(self, user_id: str, connection) -> None:
        """Register a WebSocket connection for a user"""
        if user_id not in self.websocket_connections:
            self.websocket_connections[user_id] = []
        
        self.websocket_connections[user_id].append(connection)
        logger.info(f"Registered WebSocket for user: {user_id}")
    
    def unregister_websocket(self, user_id: str, connection) -> None:
        """Unregister a WebSocket connection"""
        if user_id in self.websocket_connections:
            self.websocket_connections[user_id] = [
                c for c in self.websocket_connections[user_id] if c != connection
            ]
            if not self.websocket_connections[user_id]:
                del self.websocket_connections[user_id]
            
            logger.info(f"Unregistered WebSocket for user: {user_id}")
    
    def get_notification_history(
        self,
        user_id: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
        signal_type: Optional[TradeSignalType] = None
    ) -> List[Notification]:
        """Get notification history"""
        notifications = list(self.notification_queue)
        
        if user_id:
            notifications = [n for n in notifications if n.user_id == user_id]
        
        if signal_type:
            notifications = [n for n in notifications if n.signal_type == signal_type]

        notifications.sort(key=lambda n: n.created_at, reverse=True)
        safe_offset = max(0, int(offset))
        safe_limit = max(1, int(limit))

        return notifications[safe_offset:safe_offset + safe_limit]
    
    def mark_as_read(self, notification_id: str, user_id: Optional[str] = None) -> bool:
        """Mark notification as read"""
        for notification in self.notification_queue:
            if notification.id != notification_id:
                continue

            if user_id is not None and notification.user_id != user_id:
                continue

                notification.read = True
                notification.read_at = datetime.now(JAKARTA_TZ)
                return True
        
        return False
    
    def get_unread_count(self, user_id: str) -> int:
        """Get count of unread notifications"""
        return sum(
            1 for n in self.notification_queue
            if n.user_id == user_id and not n.read
        )
    
    def get_stats(self) -> Dict[str, Any]:
        """Get notification statistics"""
        notifications = list(self.notification_queue)
        
        return {
            "total_notifications": len(notifications),
            "pending": sum(1 for n in notifications if n.status == NotificationStatus.PENDING),
            "sent": sum(1 for n in notifications if n.status == NotificationStatus.SENT),
            "delivered": sum(1 for n in notifications if n.status == NotificationStatus.DELIVERED),
            "failed": sum(1 for n in notifications if n.status == NotificationStatus.FAILED),
            "total_alert_rules": len(self.alert_rules),
            "active_rules": sum(1 for r in self.alert_rules.values() if r.enabled),
            "registered_users": len(self.user_preferences),
            "websocket_connections": sum(
                len(conns) for conns in self.websocket_connections.values()
            ),
            "inside_bei_hours": self.is_inside_bei_hours(),
        }


# ==================== Singleton Instance ====================

_notification_manager = None


def get_notification_manager() -> NotificationManager:
    """Get or create the global notification manager instance"""
    global _notification_manager
    if _notification_manager is None:
        _notification_manager = NotificationManager()
    return _notification_manager
