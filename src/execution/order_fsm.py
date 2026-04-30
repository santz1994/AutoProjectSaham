"""Order state machine and FSM enforcement.

All transitions logged for reconciliation and compliance audit trails.
Jakarta timezone: WIB (UTC+7)
"""

from enum import Enum
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import List, Optional

JAKARTA_TZ = timezone(timedelta(hours=7))


class OrderState(str, Enum):
    """Order execution finite state machine."""
    PENDING = "PENDING"           # Initial: registered locally
    SUBMITTED = "SUBMITTED"       # Sent to broker, awaiting confirmation
    PARTIAL = "PARTIALLY_FILLED"  # Broker filled qty < requested qty
    FILLED = "FILLED"             # 100% filled
    CANCELLED = "CANCELLED"       # User or system cancelled
    REJECTED = "REJECTED"         # Broker rejected
    FAILED = "FAILED"             # Network/system failure


@dataclass
class OrderTransition:
    """Audit trail for order state changes."""
    order_id: str
    prev_state: OrderState
    next_state: OrderState
    timestamp: datetime = field(default_factory=lambda: datetime.now(JAKARTA_TZ))
    reason: str = ""
    filled_qty: int = 0
    filled_price: float = 0.0
    
    def to_dict(self):
        return {
            "order_id": self.order_id,
            "prev": self.prev_state.value,
            "next": self.next_state.value,
            "timestamp": self.timestamp.isoformat(),
            "reason": self.reason,
            "filled_qty": self.filled_qty,
            "filled_price": self.filled_price,
        }


class OrderStateMachine:
    """FSM enforcer: validates transitions, persists audit trail."""
    
    VALID_TRANSITIONS = {
        OrderState.PENDING: [OrderState.SUBMITTED, OrderState.REJECTED],
        OrderState.SUBMITTED: [OrderState.PARTIAL, OrderState.FILLED, OrderState.REJECTED, OrderState.CANCELLED],
        OrderState.PARTIAL: [OrderState.FILLED, OrderState.CANCELLED],
        OrderState.FILLED: [],  # Terminal
        OrderState.CANCELLED: [],  # Terminal
        OrderState.REJECTED: [],  # Terminal
        OrderState.FAILED: [OrderState.PENDING],  # Can retry from failed
    }
    
    def __init__(
        self,
        order_id: str,
        initial_state: OrderState = OrderState.PENDING,
        requested_qty: Optional[int] = None,
    ):
        self.order_id = order_id
        self.current_state = initial_state
        self.history: List[OrderTransition] = []
        parsed_qty = int(requested_qty) if requested_qty is not None else 0
        self.requested_qty: Optional[int] = parsed_qty if parsed_qty > 0 else None
        self.cumulative_filled_qty: int = 0
        self.avg_fill_price: float = 0.0
        self.remaining_qty: int = self.requested_qty or 0

    def _apply_fill(self, filled_qty: int, filled_price: float) -> None:
        if filled_qty <= 0:
            return

        safe_price = float(max(0.0, filled_price))
        previous_notional = float(self.cumulative_filled_qty) * float(self.avg_fill_price)
        incoming_notional = float(filled_qty) * safe_price
        self.cumulative_filled_qty += int(filled_qty)

        if self.cumulative_filled_qty > 0:
            self.avg_fill_price = float(
                (previous_notional + incoming_notional)
                / float(self.cumulative_filled_qty)
            )

        if self.requested_qty is not None:
            self.remaining_qty = max(0, int(self.requested_qty) - int(self.cumulative_filled_qty))
    
    def transition(
        self, 
        next_state: OrderState, 
        reason: str = "", 
        filled_qty: int = 0, 
        filled_price: float = 0.0
    ) -> bool:
        """
        Attempt state transition. Validates against FSM rules.
        
        Returns:
            True if transition valid and applied; False if invalid.
        """
        if next_state not in self.VALID_TRANSITIONS.get(self.current_state, []):
            raise ValueError(
                f"Invalid transition: {self.current_state.value} → {next_state.value}"
            )

        safe_fill_qty = int(filled_qty)
        if safe_fill_qty < 0:
            raise ValueError("filled_qty cannot be negative")

        if next_state == OrderState.PARTIAL:
            if self.requested_qty is not None and safe_fill_qty <= 0:
                raise ValueError("PARTIAL transition requires filled_qty > 0 when requested_qty is set")
            projected_filled = self.cumulative_filled_qty + max(0, safe_fill_qty)
            if self.requested_qty is not None and projected_filled >= self.requested_qty:
                raise ValueError("PARTIAL transition would complete the order; use FILLED")

        if next_state == OrderState.FILLED and self.requested_qty is not None:
            projected_filled = self.cumulative_filled_qty + max(0, safe_fill_qty)
            if projected_filled != self.requested_qty:
                raise ValueError(
                    f"FILLED transition requires total filled qty == requested qty ({self.requested_qty})"
                )

        if next_state in (OrderState.PARTIAL, OrderState.FILLED):
            self._apply_fill(safe_fill_qty, float(filled_price))
        
        trans = OrderTransition(
            order_id=self.order_id,
            prev_state=self.current_state,
            next_state=next_state,
            reason=reason,
            filled_qty=safe_fill_qty,
            filled_price=filled_price,
        )
        self.history.append(trans)
        self.current_state = next_state
        
        # Persist to DB (stub—implement with your DB client)
        # db.log_order_transition(trans.to_dict())
        
        return True
    
    def is_terminal(self) -> bool:
        """Check if order reached terminal state (no further changes possible)."""
        return self.current_state in (
            OrderState.FILLED,
            OrderState.CANCELLED,
            OrderState.REJECTED,
        )
