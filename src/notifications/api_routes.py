"""
FastAPI routes for Notification Management
Endpoints for alert rules, preferences, and notification retrieval
"""

from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect, status
from fastapi.responses import JSONResponse
from datetime import datetime
import logging
import json

import pytz
from .notification_service import (
    get_notification_manager,
    AlertRule, NotificationPreference, Notification,
    NotificationChannel, AlertSeverity, TradeSignalType,
    NotificationStatus
)
from .delivery_handlers import (
    NotificationChannelFactory, initialize_default_handlers
)
from src.api.auth import get_user_from_token

logger = logging.getLogger(__name__)
JAKARTA_TZ = pytz.timezone('Asia/Jakarta')

router = APIRouter(prefix="/api/notifications", tags=["notifications"])

# ==================== Helper Functions ====================

def get_manager():
    """Get the global notification manager instance"""
    return get_notification_manager()


def _extract_ws_auth_token(websocket: WebSocket) -> Optional[str]:
    query_token = str(websocket.query_params.get("token") or "").strip()
    if query_token:
        return query_token

    cookie_token = str(websocket.cookies.get("auth_token") or "").strip()
    if cookie_token:
        return cookie_token

    auth_header = str(websocket.headers.get("authorization") or "").strip()
    if auth_header.lower().startswith("bearer "):
        bearer_token = auth_header.split(" ", 1)[1].strip()
        if bearer_token:
            return bearer_token

    return None


def _authenticate_ws_user(websocket: WebSocket) -> Optional[str]:
    token = _extract_ws_auth_token(websocket)
    if not token:
        return None
    return get_user_from_token(token)


# ==================== Alert Rules Endpoints ====================

@router.post("/rules", response_model=Dict[str, Any])
async def create_alert_rule(
    rule: AlertRule,
    manager = Depends(get_manager)
) -> Dict[str, Any]:
    """Create an alert rule"""
    try:
        rule_id = manager.add_alert_rule(rule)
        return {
            "success": True,
            "rule_id": rule_id,
            "rule": manager.alert_rules[rule_id].dict(),
            "message": f"Alert rule '{rule.name}' created successfully"
        }
    except Exception as e:
        logger.error(f"Error creating alert rule: {e}")
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/rules", response_model=List[Dict[str, Any]])
async def list_alert_rules(
    symbol: Optional[str] = Query(None),
    enabled_only: bool = Query(True),
    manager = Depends(get_manager)
) -> List[Dict[str, Any]]:
    """List all alert rules"""
    rules = manager.alert_rules.values()
    
    if symbol:
        rules = [r for r in rules if r.symbol is None or r.symbol == symbol]
    
    if enabled_only:
        rules = [r for r in rules if r.enabled]
    
    return [rule.dict() for rule in rules]


@router.get("/rules/{rule_id}", response_model=Dict[str, Any])
async def get_alert_rule(
    rule_id: str,
    manager = Depends(get_manager)
) -> Dict[str, Any]:
    """Get a specific alert rule"""
    if rule_id not in manager.alert_rules:
        raise HTTPException(status_code=404, detail="Alert rule not found")
    
    return manager.alert_rules[rule_id].dict()


@router.put("/rules/{rule_id}", response_model=Dict[str, Any])
async def update_alert_rule(
    rule_id: str,
    updates: Dict[str, Any],
    manager = Depends(get_manager)
) -> Dict[str, Any]:
    """Update an alert rule"""
    try:
        rule = manager.update_alert_rule(rule_id, updates)
        return {
            "success": True,
            "rule": rule.dict(),
            "message": "Alert rule updated successfully"
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/rules/{rule_id}", response_model=Dict[str, Any])
async def delete_alert_rule(
    rule_id: str,
    manager = Depends(get_manager)
) -> Dict[str, Any]:
    """Delete (disable) an alert rule"""
    try:
        manager.delete_alert_rule(rule_id)
        return {
            "success": True,
            "message": "Alert rule deleted successfully"
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


# ==================== User Preferences Endpoints ====================

@router.post("/preferences", response_model=Dict[str, Any])
async def set_user_preferences(
    user_id: str,
    preference: NotificationPreference,
    manager = Depends(get_manager)
) -> Dict[str, Any]:
    """Set user notification preferences"""
    preference.user_id = user_id
    try:
        pref_id = manager.set_user_preference(preference)
        return {
            "success": True,
            "preference_id": pref_id,
            "message": "Preferences saved successfully"
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/preferences/{user_id}", response_model=Dict[str, Any])
async def get_user_preferences(
    user_id: str,
    manager = Depends(get_manager)
) -> Dict[str, Any]:
    """Get user notification preferences"""
    preference = manager.get_user_preference(user_id)
    
    if not preference:
        # Return default preference
        preference = NotificationPreference(user_id=user_id)
    
    return preference.dict()


@router.put("/preferences/{user_id}/channels", response_model=Dict[str, Any])
async def update_notification_channels(
    user_id: str,
    channels: List[str],
    manager = Depends(get_manager)
) -> Dict[str, Any]:
    """Update enabled notification channels for a user"""
    preference = manager.get_user_preference(user_id)
    
    if not preference:
        preference = NotificationPreference(user_id=user_id)
    
    try:
        preference.channels_enabled = [
            NotificationChannel(c) for c in channels
        ]
        manager.set_user_preference(preference)
        
        return {
            "success": True,
            "channels": [c.value for c in preference.channels_enabled],
            "message": "Notification channels updated"
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid channel: {e}")


@router.put("/preferences/{user_id}", response_model=Dict[str, Any])
async def update_user_preferences(
    user_id: str,
    updates: Dict[str, Any],
    manager = Depends(get_manager)
) -> Dict[str, Any]:
    """Update user notification preferences with partial payload"""
    preference = manager.get_user_preference(user_id)

    if not preference:
        preference = NotificationPreference(user_id=user_id)

    try:
        for key, value in updates.items():
            if key == "channels_enabled" and isinstance(value, list):
                value = [NotificationChannel(c) for c in value]
            elif key == "alert_types" and isinstance(value, list):
                value = [TradeSignalType(t) for t in value]
            elif key == "min_severity" and isinstance(value, str):
                value = AlertSeverity(value)

            if hasattr(preference, key):
                setattr(preference, key, value)

        preference.updated_at = datetime.now(JAKARTA_TZ)
        manager.set_user_preference(preference)
        return preference.dict()
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/preferences/{user_id}/quiet-hours", response_model=Dict[str, Any])
async def set_quiet_hours(
    user_id: str,
    start: str,
    end: str,
    enabled: bool = True,
    manager = Depends(get_manager)
) -> Dict[str, Any]:
    """Set quiet hours (DND) for a user"""
    preference = manager.get_user_preference(user_id)
    
    if not preference:
        preference = NotificationPreference(user_id=user_id)
    
    try:
        # Validate time format
        int(start[:2]), int(start[2:4])
        int(end[:2]), int(end[2:4])
        
        preference.quiet_hours_start = start
        preference.quiet_hours_end = end
        preference.do_not_disturb_enabled = enabled
        
        manager.set_user_preference(preference)
        
        return {
            "success": True,
            "quiet_hours": {
                "start": start,
                "end": end,
                "enabled": enabled
            },
            "message": "Quiet hours set successfully"
        }
    except (ValueError, IndexError):
        raise HTTPException(status_code=400, detail="Invalid time format (use HHmm)")


# ==================== Notification Retrieval Endpoints ====================

@router.get("/history/{user_id}", response_model=Dict[str, Any])
async def get_notification_history(
    user_id: str,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    signal_type: Optional[str] = Query(None),
    manager = Depends(get_manager)
) -> Dict[str, Any]:
    """Get notification history for a user"""
    try:
        signal_type_enum = None
        if signal_type:
            signal_type_enum = TradeSignalType(signal_type)
        
        notifications = manager.get_notification_history(
            user_id=user_id,
            limit=limit,
            offset=offset,
            signal_type=signal_type_enum
        )
        
        return {
            "success": True,
            "count": len(notifications),
            "notifications": [n.dict() for n in notifications]
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/unread/{user_id}", response_model=Dict[str, Any])
async def get_unread_count(
    user_id: str,
    manager = Depends(get_manager)
) -> Dict[str, Any]:
    """Get unread notification count for a user"""
    count = manager.get_unread_count(user_id)
    
    return {
        "success": True,
        "user_id": user_id,
        "unread_count": count
    }


@router.post("/mark-read/{notification_id}", response_model=Dict[str, Any])
async def mark_notification_read(
    notification_id: str,
    user_id: Optional[str] = None,
    manager = Depends(get_manager)
) -> Dict[str, Any]:
    """Mark a notification as read"""
    if manager.mark_as_read(notification_id, user_id):
        return {
            "success": True,
            "message": "Notification marked as read"
        }
    else:
        raise HTTPException(status_code=404, detail="Notification not found")


# ==================== Statistics & Management ====================

@router.get("/stats", response_model=Dict[str, Any])
async def get_notification_stats(
    manager = Depends(get_manager)
) -> Dict[str, Any]:
    """Get notification system statistics"""
    stats = manager.get_stats()
    stats["timestamp"] = datetime.now(JAKARTA_TZ).isoformat()
    
    return {
        "success": True,
        "stats": stats
    }


@router.get("/market-status", response_model=Dict[str, Any])
async def get_market_trading_status(
    market: str = "forex",
    symbol: Optional[str] = None,
) -> Dict[str, Any]:
    """Get current Forex/Crypto trading status."""
    from src.data.idx_fetcher import fetch_trading_status

    status = await fetch_trading_status(market=market, symbol=symbol)

    return {
        "success": True,
        "market": status.get("market", market),
        "current_time": status.get("current_time"),
        "timezone": status.get("timezone", "UTC"),
        "inside_trading_hours": bool(status.get("is_trading")),
        "trading_hours": status.get("trading_hours"),
        "next_open": status.get("next_open"),
    }


# ==================== WebSocket Endpoint ====================

@router.websocket("/ws/{user_id}")
async def websocket_notifications(
    websocket: WebSocket,
    user_id: str,
    manager = Depends(get_manager)
):
    """WebSocket endpoint for real-time notifications"""
    authenticated_user = _authenticate_ws_user(websocket)
    if not authenticated_user:
        await websocket.accept()
        await websocket.close(code=4401, reason="Unauthorized")
        return

    if str(authenticated_user) != str(user_id):
        await websocket.accept()
        await websocket.close(code=4403, reason="Forbidden")
        return

    await websocket.accept()
    manager.register_websocket(authenticated_user, websocket)
    
    try:
        # Send initial connection message
        await websocket.send_json({
            "type": "connection",
            "status": "connected",
            "user_id": authenticated_user,
            "timestamp": datetime.now(JAKARTA_TZ).isoformat()
        })
        
        # Keep connection alive and receive messages
        while True:
            data = await websocket.receive_text()
            
            try:
                message = json.loads(data)
                
                # Handle different message types
                if message.get("type") == "ping":
                    await websocket.send_json({
                        "type": "pong",
                        "timestamp": datetime.now(JAKARTA_TZ).isoformat()
                    })
                
                elif message.get("type") == "mark_read":
                    notification_id = message.get("notification_id")
                    if notification_id:
                        manager.mark_as_read(notification_id, authenticated_user)
                        await websocket.send_json({
                            "type": "read_confirmed",
                            "notification_id": notification_id
                        })
                
                elif message.get("type") == "get_unread":
                    count = manager.get_unread_count(authenticated_user)
                    await websocket.send_json({
                        "type": "unread_count",
                        "count": count
                    })
                
            except json.JSONDecodeError:
                await websocket.send_json({
                    "type": "error",
                    "message": "Invalid JSON"
                })
            except Exception as e:
                logger.error(f"WebSocket message error: {e}")
                await websocket.send_json({
                    "type": "error",
                    "message": str(e)
                })
    
    except WebSocketDisconnect:
        manager.unregister_websocket(authenticated_user, websocket)
        logger.info(f"WebSocket disconnected: {authenticated_user}")
    
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        manager.unregister_websocket(authenticated_user, websocket)


# ==================== Health Check ====================

@router.get("/health", response_model=Dict[str, Any])
async def health_check(manager = Depends(get_manager)) -> Dict[str, Any]:
    """Notification system health check"""
    stats = manager.get_stats()
    
    return {
        "success": True,
        "status": "healthy",
        "timestamp": datetime.now(JAKARTA_TZ).isoformat(),
        "handlers_registered": len(NotificationChannelFactory.get_all_handlers()),
        "total_notifications": stats.get("total_notifications", 0),
        "active_websockets": stats.get("websocket_connections", 0)
    }


# ==================== Initialization ====================

def setup_notification_routes(
    app,
    smtp_config: Optional[Dict] = None,
    slack_webhook_url: Optional[str] = None
):
    """Setup notification routes and initialize handlers"""
    
    manager = get_notification_manager()
    
    # Initialize default handlers
    initialize_default_handlers(
        manager,
        smtp_config=smtp_config,
        slack_webhook_url=slack_webhook_url
    )
    
    # Include router
    app.include_router(router)
    
    logger.info("Notification routes setup complete")
