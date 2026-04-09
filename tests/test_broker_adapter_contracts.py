# pylint: disable=protected-access

from unittest.mock import AsyncMock

import pytest

from src.brokers.ajaib import AjaibBroker
from src.brokers.base_broker import ExecutionStatus, OrderResult
from src.brokers.indopremier import IndoPremierBroker
from src.brokers.stockbit import StockbitBroker


BROKER_CONTRACT_CASES = [
    {
        "name": "stockbit",
        "cls": StockbitBroker,
        "place_payload": {
            "order": {
                "order_id": "sb-1",
                "status": "open",
                "filled_qty": 40,
                "avg_fill_price": 15750.0,
                "fills": [{"id": "fill-1"}],
            }
        },
        "place_order_id": "sb-1",
        "place_status": ExecutionStatus.ACCEPTED,
        "status_payload": {
            "order": {
                "symbol": "BBCA.JK",
                "side": "buy",
                "quantity": 100,
                "filled_qty": 25,
                "avg_fill_price": 15700.0,
                "status": "partial",
            }
        },
        "open_orders_payload": {
            "orders": [
                {"order_id": "sb-open-1", "status": "open"},
                {"order_id": "sb-open-2", "status": "partial"},
                {"order_id": "sb-done", "status": "filled"},
            ]
        },
        "open_order_ids": ["sb-open-1", "sb-open-2"],
        "status_expected": ExecutionStatus.PARTIALLY_FILLED,
        "status_symbol": "BBCA.JK",
    },
    {
        "name": "ajaib",
        "cls": AjaibBroker,
        "place_payload": {
            "data": {
                "id": "aj-1",
                "status": "partial",
                "filled_quantity": 50,
                "avg_fill_price": 8300.0,
            }
        },
        "place_order_id": "aj-1",
        "place_status": ExecutionStatus.PARTIALLY_FILLED,
        "status_payload": {
            "data": {
                "symbol": "BMRI.JK",
                "side": "sell",
                "quantity": 100,
                "filled_quantity": 100,
                "avg_fill_price": 8050.0,
                "status": "filled",
            }
        },
        "open_orders_payload": {
            "data": [
                {"id": "aj-open-1", "status": "pending"},
                {"id": "aj-open-2", "status": "accepted"},
                {"id": "aj-done", "status": "cancelled"},
            ]
        },
        "open_order_ids": ["aj-open-1", "aj-open-2"],
        "status_expected": ExecutionStatus.FILLED,
        "status_symbol": "BMRI.JK",
    },
    {
        "name": "indopremier",
        "cls": IndoPremierBroker,
        "place_payload": {
            "order": {
                "orderID": "ip-1",
                "status": "canceled",
                "filledQty": 0,
                "avgPrice": 0.0,
            }
        },
        "place_order_id": "ip-1",
        "place_status": ExecutionStatus.CANCELLED,
        "status_payload": {
            "order": {
                "code": "TLKM.JK",
                "side": "BUY",
                "qty": 200,
                "filledQty": 0,
                "avgPrice": 0.0,
                "status": "new",
            }
        },
        "open_orders_payload": {
            "orders": [
                {"orderID": "ip-open-1", "status": "new"},
                {"orderID": "ip-open-2", "status": "open"},
                {"orderID": "ip-done", "status": "rejected"},
            ]
        },
        "open_order_ids": ["ip-open-1", "ip-open-2"],
        "status_expected": ExecutionStatus.PENDING,
        "status_symbol": "TLKM.JK",
    },
]
BROKER_CASE_IDS = ["stockbit", "ajaib", "indopremier"]


def _build_broker(case):
    return case["cls"](
        api_key="test_key",
        api_secret="test_secret",
        account_id="ACC-TEST",
        access_token="token",
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "case",
    BROKER_CONTRACT_CASES,
    ids=BROKER_CASE_IDS,
)
async def test_broker_place_order_schema_contract(case):
    broker = _build_broker(case)
    broker._make_request = AsyncMock(return_value=case["place_payload"])

    result = await broker.place_order(
        symbol="BBCA.JK",
        quantity=100,
        side="buy",
        order_type="market",
    )

    assert isinstance(result, OrderResult)
    assert result.order_id == case["place_order_id"]
    assert result.status == case["place_status"]
    assert result.quantity == 100


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "case",
    BROKER_CONTRACT_CASES,
    ids=BROKER_CASE_IDS,
)
async def test_broker_get_order_status_schema_contract(case):
    broker = _build_broker(case)
    broker._make_request = AsyncMock(return_value=case["status_payload"])

    result = await broker.get_order_status("ORD-1")

    assert isinstance(result, OrderResult)
    assert result is not None
    assert result.status == case["status_expected"]
    assert result.symbol == case["status_symbol"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "case",
    BROKER_CONTRACT_CASES,
    ids=BROKER_CASE_IDS,
)
async def test_broker_place_order_schema_failure_fails_safe(case):
    broker = _build_broker(case)
    broker._make_request = AsyncMock(return_value={"unexpected": "shape"})

    result = await broker.place_order(
        symbol="BBCA.JK",
        quantity=100,
        side="buy",
    )

    assert isinstance(result, OrderResult)
    assert result.status == ExecutionStatus.FAILED
    assert "failed" in str(result.error_message or "").lower()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "case",
    BROKER_CONTRACT_CASES,
    ids=BROKER_CASE_IDS,
)
async def test_broker_make_request_uses_retry_contract(case):
    broker = _build_broker(case)
    broker.session = object()
    broker._call_with_retry = AsyncMock(return_value={"ok": True})

    payload = await broker._make_request("GET", "/contract/ping")

    assert payload == {"ok": True}
    assert broker._call_with_retry.await_count == 1

    args = broker._call_with_retry.await_args.args
    assert args[0] == f"{case['name']}:GET:/contract/ping"
    assert callable(args[1])


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "case",
    BROKER_CONTRACT_CASES,
    ids=BROKER_CASE_IDS,
)
async def test_broker_make_request_retry_failure_returns_none(case):
    broker = _build_broker(case)
    broker.session = object()
    broker._call_with_retry = AsyncMock(side_effect=RuntimeError("retry exhausted"))

    payload = await broker._make_request("POST", "/contract/ping", json={"x": 1})

    assert payload is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "case",
    BROKER_CONTRACT_CASES,
    ids=BROKER_CASE_IDS,
)
async def test_broker_list_open_orders_schema_contract(case):
    broker = _build_broker(case)
    broker._make_request = AsyncMock(return_value=case["open_orders_payload"])

    order_ids = await broker.list_open_orders(limit=200)

    assert order_ids == case["open_order_ids"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "case",
    BROKER_CONTRACT_CASES,
    ids=BROKER_CASE_IDS,
)
async def test_broker_cancel_all_open_orders_contract(case):
    broker = _build_broker(case)
    broker._make_request = AsyncMock(return_value=case["open_orders_payload"])
    broker.cancel_order = AsyncMock(return_value=True)

    report = await broker.cancel_all_open_orders(limit=200)

    assert report["status"] == "ok"
    assert report["openOrders"] == len(case["open_order_ids"])
    assert report["cancelled"] == len(case["open_order_ids"])
    assert report["failed"] == 0
