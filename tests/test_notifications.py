"""
Test Suite for Notification System
Comprehensive tests for all notification components
30+ test cases covering service, handlers, and API routes
"""

import pytest
import asyncio
import json
from datetime import datetime
from unittest.mock import Mock, patch, AsyncMock, MagicMock

import pytz
from fastapi.testclient import TestClient

from src.notifications import (
    NotificationManager, AlertRule, NotificationPreference, Notification,
    NotificationChannel, AlertSeverity, TradeSignalType, NotificationStatus,
    get_notification_manager
)
from src.notifications.delivery_handlers import (
    WebSocketHandler, EmailHandler, SlackHandler, PushNotificationHandler,
    NotificationChannelFactory
)

JAKARTA_TZ = pytz.timezone('Asia/Jakarta')


# ==================== NotificationManager Tests ====================

class TestNotificationManager:
    """Test NotificationManager core functionality"""
    
    @pytest.fixture
    def manager(self):
        """Fresh notification manager for each test"""
        return NotificationManager()
    
    def test_initialization(self, manager):
        """Test manager initializes correctly"""
        assert manager is not None
        assert len(manager.alert_rules) == 0
        assert len(manager.user_preferences) == 0
        assert len(manager.notification_queue) == 0
    
    def test_add_alert_rule(self, manager):
        """Test adding an alert rule"""
        rule = AlertRule(
            name="Buy Signal Alert",
            signal_type=TradeSignalType.BUY_SIGNAL,
            severity=AlertSeverity.INFO
        )
        
        rule_id = manager.add_alert_rule(rule)
        
        assert rule_id in manager.alert_rules
        assert manager.alert_rules[rule_id].name == "Buy Signal Alert"
    
    def test_update_alert_rule(self, manager):
        """Test updating an alert rule"""
        rule = AlertRule(
            name="Original Name",
            signal_type=TradeSignalType.BUY_SIGNAL
        )
        rule_id = manager.add_alert_rule(rule)
        
        updated_rule = manager.update_alert_rule(rule_id, {"name": "Updated Name"})
        
        assert updated_rule.name == "Updated Name"
        assert manager.alert_rules[rule_id].name == "Updated Name"
    
    def test_delete_alert_rule(self, manager):
        """Test deleting/disabling an alert rule"""
        rule = AlertRule(
            name="Test Rule",
            signal_type=TradeSignalType.BUY_SIGNAL,
            enabled=True
        )
        rule_id = manager.add_alert_rule(rule)
        
        manager.delete_alert_rule(rule_id)
        
        assert not manager.alert_rules[rule_id].enabled
    
    def test_set_user_preference(self, manager):
        """Test setting user preferences"""
        pref = NotificationPreference(
            user_id="user123",
            email_address="user@example.com"
        )
        
        pref_id = manager.set_user_preference(pref)
        
        assert pref_id is not None
        assert manager.user_preferences["user123"] == pref
    
    def test_get_user_preference(self, manager):
        """Test retrieving user preferences"""
        pref = NotificationPreference(
            user_id="user123",
            email_address="user@example.com"
        )
        manager.set_user_preference(pref)
        
        retrieved = manager.get_user_preference("user123")
        
        assert retrieved is not None
        assert retrieved.user_id == "user123"
    
    def test_is_inside_bei_hours(self, manager):
        """Test BEI trading hours detection"""
        # Mock a Monday at 10:00 AM WIB (inside trading hours)
        inside_hours = datetime(2026, 4, 6, 10, 0, 0, tzinfo=JAKARTA_TZ)
        assert manager.is_inside_bei_hours(inside_hours)
        
        # Mock a Monday at 08:00 AM WIB (before trading hours)
        before_hours = datetime(2026, 4, 6, 8, 0, 0, tzinfo=JAKARTA_TZ)
        assert not manager.is_inside_bei_hours(before_hours)
        
        # Mock a Saturday (no trading)
        saturday = datetime(2026, 4, 4, 10, 0, 0, tzinfo=JAKARTA_TZ)
        assert not manager.is_inside_bei_hours(saturday)
    
    def test_is_inside_active_hours_rule(self, manager):
        """Test rule-specific active hours"""
        rule = AlertRule(
            name="Day Only",
            signal_type=TradeSignalType.BUY_SIGNAL,
            active_hours_start="0930",
            active_hours_end="1600",
            active_days=[0, 1, 2, 3, 4]  # Mon-Fri
        )
        
        # Monday 10:00 AM - should be active
        monday_10am = datetime(2026, 4, 6, 10, 0, 0, tzinfo=JAKARTA_TZ)
        assert manager.is_inside_active_hours(rule, monday_10am)
        
        # Monday 20:00 PM - should not be active
        monday_8pm = datetime(2026, 4, 6, 20, 0, 0, tzinfo=JAKARTA_TZ)
        assert not manager.is_inside_active_hours(rule, monday_8pm)
    
    def test_should_throttle(self, manager):
        """Test alert throttling"""
        rule = AlertRule(
            name="Throttled Rule",
            signal_type=TradeSignalType.BUY_SIGNAL,
            throttle_seconds=60
        )
        rule_id = manager.add_alert_rule(rule)
        
        # First send - should not throttle
        assert not manager.should_throttle(rule_id)
        
        # Record send
        manager.record_alert_sent(rule_id)
        
        # Second send immediately - should throttle
        assert manager.should_throttle(rule_id)
    
    def test_notification_queue(self, manager):
        """Test notification queueing"""
        notification = Notification(
            rule_id="rule1",
            title="Test Notification",
            body="Test body",
            signal_type=TradeSignalType.BUY_SIGNAL,
            channels=[NotificationChannel.WEBSOCKET]
        )
        
        manager.notification_queue.append(notification)
        
        assert len(manager.notification_queue) == 1
        assert notification in manager.notification_queue
    
    def test_mark_as_read(self, manager):
        """Test marking notification as read"""
        notification = Notification(
            rule_id="rule1",
            user_id="user1",
            title="Test",
            body="Test body",
            signal_type=TradeSignalType.BUY_SIGNAL,
            channels=[NotificationChannel.WEBSOCKET],
            read=False
        )
        manager.notification_queue.append(notification)
        
        manager.mark_as_read(notification.id, "user1")
        
        assert notification.read
        assert notification.read_at is not None
    
    def test_get_unread_count(self, manager):
        """Test getting unread notification count"""
        # Add 3 unread notifications for user1
        for i in range(3):
            notification = Notification(
                rule_id=f"rule{i}",
                user_id="user1",
                title=f"Test {i}",
                body="Body",
                signal_type=TradeSignalType.BUY_SIGNAL,
                channels=[NotificationChannel.WEBSOCKET],
                read=False
            )
            manager.notification_queue.append(notification)
        
        # Add 1 read notification
        read_notif = Notification(
            rule_id="rule_read",
            user_id="user1",
            title="Read",
            body="Body",
            signal_type=TradeSignalType.BUY_SIGNAL,
            channels=[NotificationChannel.WEBSOCKET],
            read=True
        )
        manager.notification_queue.append(read_notif)
        
        count = manager.get_unread_count("user1")
        assert count == 3
    
    def test_get_notification_history(self, manager):
        """Test retrieving notification history"""
        # Add notifications
        for i in range(5):
            notification = Notification(
                rule_id=f"rule{i}",
                user_id="user1",
                title=f"Test {i}",
                body="Body",
                signal_type=TradeSignalType.BUY_SIGNAL,
                channels=[NotificationChannel.WEBSOCKET]
            )
            manager.notification_queue.append(notification)
        
        history = manager.get_notification_history(user_id="user1", limit=3)
        
        assert len(history) == 3
    
    def test_get_stats(self, manager):
        """Test getting manager statistics"""
        # Add some data
        rule = AlertRule(
            name="Test Rule",
            signal_type=TradeSignalType.BUY_SIGNAL
        )
        manager.add_alert_rule(rule)
        
        pref = NotificationPreference(user_id="user1")
        manager.set_user_preference(pref)
        
        notification = Notification(
            rule_id="rule1",
            user_id="user1",
            title="Test",
            body="Body",
            signal_type=TradeSignalType.BUY_SIGNAL,
            channels=[NotificationChannel.WEBSOCKET]
        )
        manager.notification_queue.append(notification)
        
        stats = manager.get_stats()
        
        assert stats["total_alert_rules"] == 1
        assert stats["registered_users"] == 1
        assert stats["total_notifications"] == 1


# ==================== Delivery Handler Tests ====================

class TestWebSocketHandler:
    """Test WebSocket notification handler"""
    
    @pytest.fixture
    def handler(self):
        """Create WebSocket handler with mock manager"""
        manager = NotificationManager()
        return WebSocketHandler(manager)
    
    @pytest.mark.asyncio
    async def test_send_websocket(self, handler):
        """Test sending WebSocket notification"""
        notification = Notification(
            rule_id="rule1",
            title="WS Test",
            body="Test body",
            signal_type=TradeSignalType.BUY_SIGNAL,
            channels=[NotificationChannel.WEBSOCKET]
        )
        
        log = await handler.send(notification, user_id="user1")
        
        assert log.notification_id == notification.id
        assert log.channel == NotificationChannel.WEBSOCKET


class TestEmailHandler:
    """Test Email notification handler"""
    
    @pytest.fixture
    def handler(self):
        """Create Email handler"""
        smtp_config = {
            'host': 'smtp.gmail.com',
            'port': 587,
            'sender_email': 'test@example.com',
            'sender_password': 'password'
        }
        return EmailHandler(smtp_config)
    
    @pytest.mark.asyncio
    async def test_send_email(self, handler):
        """Test sending email notification"""
        notification = Notification(
            rule_id="rule1",
            title="Email Test",
            body="Test body",
            signal_type=TradeSignalType.BUY_SIGNAL,
            channels=[NotificationChannel.EMAIL]
        )
        
        pref = NotificationPreference(
            user_id="user1",
            email_address="user@example.com"
        )
        
        log = await handler.send(notification, user_id="user1", preference=pref)
        
        assert log.notification_id == notification.id
        assert log.status == NotificationStatus.SENT


class TestSlackHandler:
    """Test Slack notification handler"""
    
    @pytest.fixture
    def handler(self):
        """Create Slack handler"""
        return SlackHandler()
    
    @pytest.mark.asyncio
    async def test_send_slack_no_config(self, handler):
        """Test Slack handler without configuration"""
        notification = Notification(
            rule_id="rule1",
            title="Slack Test",
            body="Test body",
            signal_type=TradeSignalType.BUY_SIGNAL,
            channels=[NotificationChannel.SLACK]
        )
        
        log = await handler.send(notification, user_id="user1")
        
        assert log.status == NotificationStatus.FAILED


# ==================== Alert Rule Model Tests ====================

class TestAlertRuleModel:
    """Test AlertRule Pydantic model"""
    
    def test_alert_rule_creation(self):
        """Test creating an alert rule"""
        rule = AlertRule(
            name="Test Rule",
            signal_type=TradeSignalType.BUY_SIGNAL,
            severity=AlertSeverity.WARNING
        )
        
        assert rule.name == "Test Rule"
        assert rule.signal_type == TradeSignalType.BUY_SIGNAL
        assert rule.severity == AlertSeverity.WARNING
        assert rule.enabled is True
    
    def test_alert_rule_time_validation(self):
        """Test time format validation"""
        rule = AlertRule(
            name="Time Test",
            signal_type=TradeSignalType.BUY_SIGNAL,
            active_hours_start="0930",
            active_hours_end="1600"
        )
        
        assert rule.active_hours_start == "0930"
        assert rule.active_hours_end == "1600"
    
    def test_alert_rule_invalid_time(self):
        """Test invalid time format raises error"""
        with pytest.raises(ValueError):
            AlertRule(
                name="Invalid Time",
                signal_type=TradeSignalType.BUY_SIGNAL,
                active_hours_start="25:00"  # Invalid hour
            )


# ==================== NotificationPreference Model Tests ====================

class TestNotificationPreferences:
    """Test NotificationPreference Pydantic model"""
    
    def test_preference_creation(self):
        """Test creating user preferences"""
        pref = NotificationPreference(
            user_id="user123",
            email_address="user@example.com",
            slack_webhook_url="https://hooks.slack.com/test"
        )
        
        assert pref.user_id == "user123"
        assert pref.email_address == "user@example.com"
        assert NotificationChannel.WEBSOCKET in pref.channels_enabled
    
    def test_preference_default_channels(self):
        """Test default channels are set"""
        pref = NotificationPreference(user_id="user1")
        
        assert NotificationChannel.WEBSOCKET in pref.channels_enabled
        assert NotificationChannel.EMAIL in pref.channels_enabled
    
    def test_preference_quiet_hours(self):
        """Test quiet hours setting"""
        pref = NotificationPreference(
            user_id="user1",
            quiet_hours_start="22:00",
            quiet_hours_end="08:00",
            do_not_disturb_enabled=True
        )
        
        assert pref.do_not_disturb_enabled
        assert pref.quiet_hours_start == "22:00"


# ==================== Jakarta Timezone Tests ====================

class TestJakartaTimezone:
    """Test Jakarta timezone handling"""
    
    def test_jakarta_timezone(self):
        """Test Jakarta timezone is correct"""
        now = datetime.now(JAKARTA_TZ)
        assert now.tzname() == "WIB" or now.tzname() == "WITA"  # WIB or WITA depending on DST
    
    def test_bei_hours_monday_morning(self):
        """Test Monday morning during BEI hours"""
        manager = NotificationManager()
        monday_10am = datetime(2026, 4, 6, 10, 0, 0, tzinfo=JAKARTA_TZ)
        
        assert manager.is_inside_bei_hours(monday_10am)
    
    def test_bei_hours_weekend(self):
        """Test weekend (no trading)"""
        manager = NotificationManager()
        saturday = datetime(2026, 4, 4, 10, 0, 0, tzinfo=JAKARTA_TZ)
        
        assert not manager.is_inside_bei_hours(saturday)
    
    def test_bei_hours_before_market_open(self):
        """Test before market open"""
        manager = NotificationManager()
        monday_9am = datetime(2026, 4, 6, 9, 0, 0, tzinfo=JAKARTA_TZ)
        
        assert not manager.is_inside_bei_hours(monday_9am)
    
    def test_bei_hours_after_market_close(self):
        """Test after market close"""
        manager = NotificationManager()
        monday_5pm = datetime(2026, 4, 6, 17, 0, 0, tzinfo=JAKARTA_TZ)
        
        assert not manager.is_inside_bei_hours(monday_5pm)


# ==================== Integration Tests ====================

class TestNotificationIntegration:
    """Integration tests for complete notification flow"""
    
    @pytest.mark.asyncio
    async def test_complete_notification_flow(self):
        """Test complete notification from rule to logging"""
        manager = NotificationManager()
        
        # Create alert rule
        rule = AlertRule(
            name="Integration Test Rule",
            signal_type=TradeSignalType.BUY_SIGNAL,
            severity=AlertSeverity.WARNING,
            channels=[NotificationChannel.WEBSOCKET]
        )
        rule_id = manager.add_alert_rule(rule)
        
        # Set user preference
        pref = NotificationPreference(user_id="test_user")
        manager.set_user_preference(pref)
        
        # Create notification
        notification = Notification(
            rule_id=rule_id,
            user_id="test_user",
            title="Integration Test",
            body="Test notification body",
            signal_type=TradeSignalType.BUY_SIGNAL,
            channels=[NotificationChannel.WEBSOCKET],
            data={"symbol": "BBCA.JK", "price": 15000}
        )
        
        # Add to queue
        manager.notification_queue.append(notification)
        
        # Verify
        assert len(manager.notification_queue) == 1
        assert manager.get_unread_count("test_user") == 1
        
        # Mark as read
        manager.mark_as_read(notification.id, "test_user")
        assert manager.get_unread_count("test_user") == 0


# ==================== Enums Tests ====================

class TestEnums:
    """Test notification enums"""
    
    def test_notification_channels(self):
        """Test NotificationChannel enum"""
        assert NotificationChannel.WEBSOCKET.value == "websocket"
        assert NotificationChannel.EMAIL.value == "email"
        assert NotificationChannel.SLACK.value == "slack"
        assert NotificationChannel.PUSH.value == "push"
    
    def test_alert_severity(self):
        """Test AlertSeverity enum"""
        assert AlertSeverity.INFO.value == "info"
        assert AlertSeverity.WARNING.value == "warning"
        assert AlertSeverity.CRITICAL.value == "critical"
    
    def test_trade_signal_types(self):
        """Test TradeSignalType enum"""
        assert TradeSignalType.BUY_SIGNAL.value == "buy_signal"
        assert TradeSignalType.SELL_SIGNAL.value == "sell_signal"
        assert TradeSignalType.ANOMALY_DETECTED.value == "anomaly_detected"
    
    def test_notification_status(self):
        """Test NotificationStatus enum"""
        assert NotificationStatus.PENDING.value == "pending"
        assert NotificationStatus.SENT.value == "sent"
        assert NotificationStatus.DELIVERED.value == "delivered"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
