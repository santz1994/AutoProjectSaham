"""
Notifications Package
Real-time notification system with WebSocket, Email, Slack, and Push support
Jakarta timezone aware, BEI trading hours compliant
"""

from .notification_service import (
    NotificationManager, AlertRule, NotificationPreference, Notification,
    NotificationChannel, AlertSeverity, TradeSignalType, NotificationStatus,
    NotificationLog, get_notification_manager,
    BEI_START_HOUR, BEI_START_MINUTE, BEI_END_HOUR, BEI_END_MINUTE,
    BEI_TRADING_DAYS, JAKARTA_TZ
)
from .delivery_handlers import (
    NotificationHandler, WebSocketHandler, EmailHandler, SlackHandler,
    PushNotificationHandler, NotificationChannelFactory, initialize_default_handlers
)
from .api_routes import setup_notification_routes, router

__version__ = "1.0.0"

__all__ = [
    # Service classes
    'NotificationManager',
    'NotificationChannelFactory',
    
    # Data models
    'AlertRule',
    'NotificationPreference',
    'Notification',
    'NotificationLog',
    
    # Enums
    'NotificationChannel',
    'AlertSeverity',
    'TradeSignalType',
    'NotificationStatus',
    
    # Handlers
    'NotificationHandler',
    'WebSocketHandler',
    'EmailHandler',
    'SlackHandler',
    'PushNotificationHandler',
    
    # Functions
    'get_notification_manager',
    'initialize_default_handlers',
    'setup_notification_routes',
    
    # API
    'router',
    
    # Constants
    'JAKARTA_TZ',
    'BEI_START_HOUR',
    'BEI_START_MINUTE',
    'BEI_END_HOUR',
    'BEI_END_MINUTE',
    'BEI_TRADING_DAYS',
]
