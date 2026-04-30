from src.execution.manager import ExecutionManager


class _BrokerWithActiveOrders:
    def __init__(self):
        self.positions = {}
        self.cash = 1000000.0

    def get_active_orders(self):
        return [
            {
                "id": "BKR-1",
                "symbol": "BTCUSDT",
                "side": "buy",
                "qty": 2,
                "price": 9000,
                "status": "OPEN",
            },
            {
                "id": "BKR-2",
                "symbol": "EURUSD=X",
                "side": "sell",
                "quantity": 1,
                "limit_price": 7000,
                "status": "PENDING",
            },
            {
                "id": "BKR-3",
                "symbol": "XAUUSD=X",
                "side": "buy",
                "qty": 0,
                "price": 2500,
                "status": "OPEN",
            },
        ]


class _BrokerWithoutActiveOrdersApi:
    def __init__(self):
        self.positions = {}
        self.cash = 1000000.0


def test_startup_sync_blocks_pre_trade_until_completed():
    manager = ExecutionManager(
        broker=_BrokerWithActiveOrders(),
        require_startup_sync=True,
    )

    ok_before, reason_before = manager.pre_trade_check(
        symbol="BTCUSDT",
        side="buy",
        qty=1,
        price=9000,
    )
    assert ok_before is False
    assert "startup sync pending" in reason_before.lower()

    report = manager.sync_open_orders_on_startup(limit=10)
    assert report["completed"] is True
    assert report["status"] == "ok"
    assert report["sourceOpenOrders"] == 3
    assert report["importedPending"] == 2
    assert report["skipped"] == 1

    pending = manager.get_pending_orders()
    assert len(pending) == 2

    ok_after, reason_after = manager.pre_trade_check(
        symbol="BTCUSDT",
        side="buy",
        qty=1,
        price=9000,
    )
    assert ok_after is True
    assert reason_after == "ok"


def test_startup_sync_completes_when_broker_lacks_open_orders_api():
    manager = ExecutionManager(
        broker=_BrokerWithoutActiveOrdersApi(),
        require_startup_sync=True,
    )

    report = manager.sync_open_orders_on_startup()

    assert report["completed"] is True
    assert report["status"] == "broker_active_orders_api_unavailable"

    sync_status = manager.get_startup_sync_status()
    assert sync_status["completed"] is True
    assert sync_status["required"] is True
