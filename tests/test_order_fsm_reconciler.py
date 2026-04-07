import pytest

from src.execution.order_fsm import OrderState, OrderStateMachine
from src.execution.reconciler import TradeReconciler


def test_order_fsm_partial_then_cancel_tracks_remaining_qty():
    fsm = OrderStateMachine("ORD-001", requested_qty=100)

    fsm.transition(OrderState.SUBMITTED, reason="sent_to_broker")
    fsm.transition(
        OrderState.PARTIAL,
        reason="partial_fill",
        filled_qty=40,
        filled_price=100.0,
    )

    assert fsm.cumulative_filled_qty == 40
    assert fsm.remaining_qty == 60
    assert fsm.avg_fill_price == pytest.approx(100.0)

    fsm.transition(OrderState.CANCELLED, reason="cancel_remaining")
    assert fsm.is_terminal()


def test_order_fsm_partial_rejects_full_completion_payload():
    fsm = OrderStateMachine("ORD-002", requested_qty=50)
    fsm.transition(OrderState.SUBMITTED, reason="sent_to_broker")

    with pytest.raises(ValueError):
        fsm.transition(
            OrderState.PARTIAL,
            reason="invalid_partial",
            filled_qty=50,
            filled_price=101.0,
        )


@pytest.mark.asyncio
async def test_reconciler_marks_partial_fill_when_volume_less_than_requested():
    class DummyDB:
        def __init__(self):
            self.updates = []

        async def get_orders_by_status(self, status):
            return [{"id": "ORD-100", "symbol": "BBCA", "quantity": 100}]

        async def update_order_status(self, order_id, **kwargs):
            self.updates.append({"order_id": order_id, **kwargs})

    class DummyBroker:
        async def get_active_orders(self):
            return []

        async def get_trade_history(self, symbol):
            return [
                {"order_id": "ORD-100", "price": 15000.0, "volume": 40},
            ]

    db = DummyDB()
    broker = DummyBroker()

    reconciler = TradeReconciler(broker, db)
    await reconciler.reconcile_unsettled_orders()

    assert len(db.updates) == 1
    assert db.updates[0]["status"] == "PARTIALLY_FILLED"
    assert db.updates[0]["filled_qty"] == 40
    assert db.updates[0]["filled_price"] == pytest.approx(15000.0)


@pytest.mark.asyncio
async def test_reconciler_aggregates_multi_fill_to_final_filled():
    class DummyDB:
        def __init__(self):
            self.updates = []

        async def get_orders_by_status(self, status):
            return [{"id": "ORD-200", "symbol": "BBCA", "qty": 100}]

        async def update_order_status(self, order_id, **kwargs):
            self.updates.append({"order_id": order_id, **kwargs})

    class DummyBroker:
        async def get_active_orders(self):
            return []

        async def get_trade_history(self, symbol):
            return [
                {"order_id": "ORD-200", "price": 100.0, "volume": 30},
                {"order_id": "ORD-200", "price": 110.0, "volume": 70},
            ]

    db = DummyDB()
    broker = DummyBroker()

    reconciler = TradeReconciler(broker, db)
    await reconciler.reconcile_unsettled_orders()

    assert len(db.updates) == 1
    assert db.updates[0]["status"] == "FILLED"
    assert db.updates[0]["filled_qty"] == 100
    assert db.updates[0]["filled_price"] == pytest.approx(107.0)
