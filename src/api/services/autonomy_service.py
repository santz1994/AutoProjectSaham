"""Autonomy Slider & Kill-Switch Enhancement Service.

Provides multi-level autonomy control for the trading system:
- Level 1: Signal/Notification only (no auto-execution)
- Level 2: AI drafts orders, human approves (human-in-the-loop)
- Level 3: Full autonomous execution

Part of Phase G: Autonomy Slider & Kill-Switch Enhancement.
"""

from __future__ import annotations

import logging
import os
import threading
import time
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


class AutonomyLevel(IntEnum):
    """Trading autonomy levels."""
    SIGNAL_ONLY = 1      # Only generate signals/notifications
    HUMAN_CONFIRM = 2    # AI drafts orders, human approves
    FULL_AUTO = 3        # Fully autonomous execution


@dataclass
class PendingOrder:
    """An order drafted by AI awaiting human confirmation."""
    order_id: str
    symbol: str
    side: str  # "BUY" or "SELL"
    quantity: float
    price: Optional[float]
    target_fraction: float
    stop_loss_distance: Optional[float]
    reason: str
    ai_confidence: float
    regime: str
    created_at: float = field(default_factory=time.time)
    status: str = "pending"  # pending, approved, rejected, expired
    approved_at: Optional[float] = None
    expires_at: Optional[float] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "order_id": self.order_id,
            "symbol": self.symbol,
            "side": self.side,
            "quantity": self.quantity,
            "price": self.price,
            "target_fraction": self.target_fraction,
            "stop_loss_distance": self.stop_loss_distance,
            "reason": self.reason,
            "ai_confidence": round(self.ai_confidence, 4),
            "regime": self.regime,
            "status": self.status,
            "created_at": self.created_at,
            "approved_at": self.approved_at,
            "expires_at": self.expires_at,
            "age_seconds": time.time() - self.created_at,
        }


@dataclass
class AutonomyState:
    """Current autonomy system state."""
    level: AutonomyLevel
    kill_switch_active: bool
    pending_orders_count: int
    total_orders_drafted: int
    total_orders_approved: int
    total_orders_rejected: int
    total_orders_expired: int
    total_auto_executed: int
    last_level_change_at: Optional[float]
    last_kill_switch_at: Optional[float]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "level": self.level.value,
            "level_name": self.level.name,
            "kill_switch_active": self.kill_switch_active,
            "pending_orders_count": self.pending_orders_count,
            "total_orders_drafted": self.total_orders_drafted,
            "total_orders_approved": self.total_orders_approved,
            "total_orders_rejected": self.total_orders_rejected,
            "total_orders_expired": self.total_orders_expired,
            "total_auto_executed": self.total_auto_executed,
            "last_level_change_at": self.last_level_change_at,
            "last_kill_switch_at": self.last_kill_switch_at,
        }


class AutonomyService:
    """Autonomy Slider Service managing trading execution levels.

    Thread-safe service that controls whether the AI trading system:
    - Only generates signals (Level 1)
    - Drafts orders for human approval (Level 2)
    - Executes autonomously (Level 3)

    Includes kill-switch for emergency stop of all trading activity.
    """

    def __init__(
        self,
        initial_level: AutonomyLevel = AutonomyLevel.SIGNAL_ONLY,
        order_expiry_seconds: float = 300.0,
        max_pending_orders: int = 50,
    ):
        """
        Args:
            initial_level: Starting autonomy level (default: safest — signal only).
            order_expiry_seconds: Seconds before pending orders auto-expire.
            max_pending_orders: Maximum number of pending orders allowed.
        """
        self._level = initial_level
        self._kill_switch = False
        self._order_expiry = order_expiry_seconds
        self._max_pending = max_pending_orders

        # Pending orders (Level 2)
        self._pending_orders: Dict[str, PendingOrder] = {}
        self._order_counter = 0

        # Stats
        self._total_drafted = 0
        self._total_approved = 0
        self._total_rejected = 0
        self._total_expired = 0
        self._total_auto_executed = 0
        self._last_level_change: Optional[float] = None
        self._last_kill_switch: Optional[float] = None

        # Callbacks
        self._on_order_approved: Optional[Callable] = None
        self._on_order_rejected: Optional[Callable] = None
        self._on_auto_execute: Optional[Callable] = None

        # Thread safety
        self._lock = threading.RLock()

        # Allowed admin roles (from env)
        self._admin_roles = self._parse_admin_roles()

        logger.info(
            "AutonomyService initialized: level=%s, order_expiry=%.0fs",
            self._level.name, order_expiry_seconds,
        )

    @property
    def level(self) -> AutonomyLevel:
        with self._lock:
            return self._level

    @property
    def kill_switch_active(self) -> bool:
        with self._lock:
            return self._kill_switch

    def set_level(self, level: int, admin_token: Optional[str] = None) -> Dict[str, Any]:
        """Change the autonomy level.

        Args:
            level: New autonomy level (1, 2, or 3).
            admin_token: Optional admin authentication token.

        Returns:
            Dict with result of the level change.
        """
        with self._lock:
            try:
                new_level = AutonomyLevel(level)
            except ValueError:
                return {
                    "success": False,
                    "error": f"Invalid autonomy level: {level}. Must be 1, 2, or 3.",
                }

            old_level = self._level
            self._level = new_level
            self._last_level_change = time.time()

            logger.info(
                "Autonomy level changed: %s → %s",
                old_level.name, new_level.name,
            )

            # If downgrading from auto, expire all pending orders
            if new_level < AutonomyLevel.HUMAN_CONFIRM:
                expired_count = self._expire_all_pending()
            else:
                expired_count = 0

            return {
                "success": True,
                "old_level": old_level.value,
                "new_level": new_level.value,
                "new_level_name": new_level.name,
                "expired_pending_orders": expired_count,
            }

    def activate_kill_switch(self, reason: str = "Manual activation") -> Dict[str, Any]:
        """Emergency kill-switch: halt all trading activity immediately."""
        with self._lock:
            was_active = self._kill_switch
            self._kill_switch = True
            self._last_kill_switch = time.time()

            # Expire all pending orders
            expired = self._expire_all_pending()

            logger.critical(
                "KILL SWITCH ACTIVATED: %s (expired %d pending orders)",
                reason, expired,
            )

            return {
                "success": True,
                "was_already_active": was_active,
                "reason": reason,
                "expired_pending_orders": expired,
                "timestamp": self._last_kill_switch,
            }

    def deactivate_kill_switch(self) -> Dict[str, Any]:
        """Deactivate the kill-switch and resume normal operations."""
        with self._lock:
            was_active = self._kill_switch
            self._kill_switch = False

            logger.info("Kill switch deactivated")

            return {
                "success": True,
                "was_active": was_active,
            }

    def process_trade_signal(
        self,
        symbol: str,
        side: str,
        quantity: float,
        target_fraction: float,
        reason: str,
        ai_confidence: float = 0.0,
        regime: str = "unknown",
        price: Optional[float] = None,
        stop_loss_distance: Optional[float] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Process a trade signal based on current autonomy level.

        - Level 1: Return signal only (no execution, no draft)
        - Level 2: Draft order for human approval
        - Level 3: Return execute signal immediately

        Returns:
            Dict with action taken and details.
        """
        with self._lock:
            # Kill-switch check
            if self._kill_switch:
                return {
                    "action": "blocked",
                    "reason": "Kill switch is active. All trading halted.",
                    "symbol": symbol,
                    "side": side,
                }

            if self._level == AutonomyLevel.SIGNAL_ONLY:
                return {
                    "action": "signal_only",
                    "symbol": symbol,
                    "side": side,
                    "quantity": quantity,
                    "target_fraction": target_fraction,
                    "reason": reason,
                    "ai_confidence": ai_confidence,
                    "regime": regime,
                    "message": "Signal generated. No order placed (Level 1: Signal Only).",
                }

            elif self._level == AutonomyLevel.HUMAN_CONFIRM:
                # Draft order
                if len(self._pending_orders) >= self._max_pending:
                    self._expire_oldest_pending()

                order_id = self._generate_order_id()
                order = PendingOrder(
                    order_id=order_id,
                    symbol=symbol,
                    side=side,
                    quantity=quantity,
                    price=price,
                    target_fraction=target_fraction,
                    stop_loss_distance=stop_loss_distance,
                    reason=reason,
                    ai_confidence=ai_confidence,
                    regime=regime,
                    expires_at=time.time() + self._order_expiry,
                    metadata=metadata or {},
                )
                self._pending_orders[order_id] = order
                self._total_drafted += 1

                logger.info(
                    "Order drafted: %s %s %s (qty=%.6f, conf=%.2f)",
                    order_id, side, symbol, quantity, ai_confidence,
                )

                return {
                    "action": "order_drafted",
                    "order": order.to_dict(),
                    "message": "Order drafted. Awaiting human approval (Level 2).",
                }

            else:  # FULL_AUTO
                self._total_auto_executed += 1

                logger.info(
                    "AUTO-EXECUTE: %s %s %s (qty=%.6f, conf=%.2f)",
                    side, symbol, quantity, quantity, ai_confidence,
                )

                return {
                    "action": "auto_execute",
                    "symbol": symbol,
                    "side": side,
                    "quantity": quantity,
                    "target_fraction": target_fraction,
                    "stop_loss_distance": stop_loss_distance,
                    "reason": reason,
                    "ai_confidence": ai_confidence,
                    "regime": regime,
                    "message": "Auto-executed (Level 3: Full Auto).",
                }

    def approve_order(self, order_id: str) -> Dict[str, Any]:
        """Human approves a pending order (Level 2)."""
        with self._lock:
            order = self._pending_orders.get(order_id)
            if order is None:
                return {"success": False, "error": f"Order {order_id} not found."}
            if order.status != "pending":
                return {"success": False, "error": f"Order {order_id} is {order.status}, not pending."}

            # Check expiry
            if order.expires_at and time.time() > order.expires_at:
                order.status = "expired"
                self._total_expired += 1
                return {"success": False, "error": f"Order {order_id} has expired."}

            order.status = "approved"
            order.approved_at = time.time()
            self._total_approved += 1
            del self._pending_orders[order_id]

            logger.info("Order approved: %s", order_id)

            return {
                "success": True,
                "order": order.to_dict(),
                "message": "Order approved for execution.",
            }

    def reject_order(self, order_id: str, reason: str = "") -> Dict[str, Any]:
        """Human rejects a pending order (Level 2)."""
        with self._lock:
            order = self._pending_orders.get(order_id)
            if order is None:
                return {"success": False, "error": f"Order {order_id} not found."}
            if order.status != "pending":
                return {"success": False, "error": f"Order {order_id} is {order.status}, not pending."}

            order.status = "rejected"
            self._total_rejected += 1
            del self._pending_orders[order_id]

            logger.info("Order rejected: %s (reason: %s)", order_id, reason)

            return {
                "success": True,
                "order": order.to_dict(),
                "reason": reason,
            }

    def get_pending_orders(self) -> List[Dict[str, Any]]:
        """Get all pending orders."""
        with self._lock:
            self._cleanup_expired()
            return [o.to_dict() for o in self._pending_orders.values()]

    def get_state(self) -> AutonomyState:
        """Get current autonomy system state."""
        with self._lock:
            self._cleanup_expired()
            return AutonomyState(
                level=self._level,
                kill_switch_active=self._kill_switch,
                pending_orders_count=len(self._pending_orders),
                total_orders_drafted=self._total_drafted,
                total_orders_approved=self._total_approved,
                total_orders_rejected=self._total_rejected,
                total_orders_expired=self._total_expired,
                total_auto_executed=self._total_auto_executed,
                last_level_change_at=self._last_level_change,
                last_kill_switch_at=self._last_kill_switch,
            )

    def get_stats(self) -> Dict[str, Any]:
        """Return service statistics."""
        return self.get_state().to_dict()

    # --- Internal helpers ---

    def _generate_order_id(self) -> str:
        self._order_counter += 1
        return f"ORD-{int(time.time())}-{self._order_counter:04d}"

    def _expire_all_pending(self) -> int:
        count = len(self._pending_orders)
        for order in self._pending_orders.values():
            order.status = "expired"
            self._total_expired += 1
        self._pending_orders.clear()
        return count

    def _expire_oldest_pending(self):
        if not self._pending_orders:
            return
        oldest_id = min(
            self._pending_orders,
            key=lambda k: self._pending_orders[k].created_at,
        )
        self._pending_orders[oldest_id].status = "expired"
        self._total_expired += 1
        del self._pending_orders[oldest_id]

    def _cleanup_expired(self):
        now = time.time()
        expired_ids = [
            oid for oid, order in self._pending_orders.items()
            if order.expires_at and now > order.expires_at
        ]
        for oid in expired_ids:
            self._pending_orders[oid].status = "expired"
            self._total_expired += 1
            del self._pending_orders[oid]

    @staticmethod
    def _parse_admin_roles() -> list:
        raw = os.environ.get("ADMIN_ROLES", "admin,superadmin")
        return [r.strip().lower() for r in raw.split(",") if r.strip()]