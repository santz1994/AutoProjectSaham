import uuid

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from src.api import server


pytestmark = pytest.mark.skipif(
    not getattr(server, "FASTAPI_AVAILABLE", False),
    reason="FastAPI not available",
)


def _login(client: TestClient, username: str) -> None:
    password = "demo123"
    register_res = client.post(
        "/auth/register",
        json={"username": username, "password": password},
    )
    assert register_res.status_code in {200, 400}

    login_res = client.post(
        "/auth/login",
        json={"username": username, "password": password},
    )
    assert login_res.status_code == 200


@pytest.fixture
def client() -> TestClient:
    return TestClient(server.app)


def test_ws_events_requires_auth(client: TestClient):
    with pytest.raises(WebSocketDisconnect) as exc:
        with client.websocket_connect("/ws/events") as websocket:
            websocket.receive_json()

    assert exc.value.code == 4401


def test_ws_charts_requires_auth(client: TestClient):
    with pytest.raises(WebSocketDisconnect) as exc:
        with client.websocket_connect("/ws/charts/BTCUSDT") as websocket:
            websocket.receive_json()

    assert exc.value.code == 4401


def test_notifications_ws_forbids_user_mismatch(client: TestClient):
    username = f"ws_user_{uuid.uuid4().hex[:8]}"
    _login(client, username)

    with pytest.raises(WebSocketDisconnect) as exc:
        with client.websocket_connect("/api/notifications/ws/other_user") as websocket:
            websocket.receive_json()

    assert exc.value.code == 4403


def test_notifications_ws_accepts_authenticated_user(client: TestClient):
    username = f"ws_user_{uuid.uuid4().hex[:8]}"
    _login(client, username)

    with client.websocket_connect(f"/api/notifications/ws/{username}") as websocket:
        payload = websocket.receive_json()
        assert payload["type"] == "connection"
        assert payload["status"] == "connected"
        assert payload["user_id"] == username
