import time
import uuid

import pytest
from fastapi.testclient import TestClient

from src.api import server


pytestmark = pytest.mark.skipif(
    not getattr(server, "FASTAPI_AVAILABLE", False),
    reason="FastAPI not available",
)


def _register(client: TestClient, username: str, password: str = "demo123") -> None:
    response = client.post(
        "/auth/register",
        json={"username": username, "password": password},
    )
    assert response.status_code in {200, 400}


def _login(
    client: TestClient,
    username: str,
    password: str = "demo123",
    remember_me: bool = False,
    two_factor_code: str = "",
):
    return client.post(
        "/auth/login",
        json={
            "username": username,
            "password": password,
            "rememberMe": bool(remember_me),
            **({"twoFactorCode": two_factor_code} if str(two_factor_code).strip() else {}),
        },
    )


def _cookie_expiry_epoch(response, cookie_name: str) -> int:
    jar = getattr(response.cookies, "jar", None)
    if jar is None:
        return 0

    for cookie in jar:
        if str(cookie.name) == cookie_name:
            return int(cookie.expires or 0)
    return 0


@pytest.fixture
def client() -> TestClient:
    return TestClient(server.app)


def test_auth_login_sets_csrf_cookie_and_role_claim(client: TestClient):
    username = f"auth_user_{uuid.uuid4().hex[:8]}"
    _register(client, username)

    login_response = _login(client, username)

    assert login_response.status_code == 200
    assert "auth_token" in login_response.cookies
    assert "csrf_token" in login_response.cookies

    me_response = client.get("/auth/me")
    assert me_response.status_code == 200
    me_payload = me_response.json()
    assert me_payload["username"] == username
    assert me_payload["role"] == "trader"


def test_auth_login_remember_me_extends_session_ttl(monkeypatch, client: TestClient):
    monkeypatch.setenv("AUTH_TTL_SECONDS", "3600")
    monkeypatch.setenv("AUTH_REMEMBER_ME_TTL_SECONDS", "7200")

    username = f"auth_user_{uuid.uuid4().hex[:8]}"
    _register(client, username)

    short_session = _login(client, username, remember_me=False)
    long_session = _login(client, username, remember_me=True)

    assert short_session.status_code == 200
    assert long_session.status_code == 200

    short_expiry = _cookie_expiry_epoch(short_session, "auth_token")
    long_expiry = _cookie_expiry_epoch(long_session, "auth_token")

    now_epoch = int(time.time())
    assert short_expiry > now_epoch
    assert long_expiry > short_expiry


def test_admin_guard_and_csrf_protect_bot_start(monkeypatch, client: TestClient):
    monkeypatch.setenv("AUTOSAHAM_ADMIN_GUARD_ENABLED", "true")
    monkeypatch.setenv("AUTOSAHAM_CSRF_PROTECTION_ENABLED", "true")

    admin_user = f"ops_admin_{uuid.uuid4().hex[:8]}"
    monkeypatch.setenv("AUTOSAHAM_KILL_SWITCH_ADMIN_USERS", admin_user)

    # No session -> unauthorized when admin guard is enabled.
    unauth_response = client.post("/api/bot/start")
    assert unauth_response.status_code == 401

    _register(client, admin_user)
    login_response = _login(client, admin_user)
    assert login_response.status_code == 200

    # Session exists but missing CSRF header -> forbidden.
    no_csrf_response = client.post("/api/bot/start")
    assert no_csrf_response.status_code == 403

    csrf_token = client.cookies.get("csrf_token")
    assert csrf_token

    ok_response = client.post(
        "/api/bot/start",
        headers={"X-CSRF-Token": csrf_token},
    )
    assert ok_response.status_code == 200
    assert ok_response.json().get("status") == "started"


def test_login_requires_two_factor_for_configured_roles(monkeypatch, client: TestClient):
    monkeypatch.setenv("AUTOSAHAM_LOGIN_2FA_ENABLED", "true")
    monkeypatch.setenv("AUTOSAHAM_LOGIN_2FA_REQUIRED_ROLES", "trader")
    monkeypatch.setenv("AUTOSAHAM_LOGIN_2FA_CODE", "135790")

    username = f"auth_user_{uuid.uuid4().hex[:8]}"
    _register(client, username)

    missing_code = _login(client, username)
    assert missing_code.status_code == 401
    assert missing_code.json().get("detail") == "two_factor_required"

    invalid_code = _login(client, username, two_factor_code="000000")
    assert invalid_code.status_code == 401
    assert invalid_code.json().get("detail") == "invalid_two_factor_code"

    valid_code = _login(client, username, two_factor_code="135790")
    assert valid_code.status_code == 200


def test_login_two_factor_required_but_not_configured(monkeypatch, client: TestClient):
    monkeypatch.setenv("AUTOSAHAM_LOGIN_2FA_ENABLED", "true")
    monkeypatch.setenv("AUTOSAHAM_LOGIN_2FA_REQUIRED_ROLES", "trader")
    monkeypatch.delenv("AUTOSAHAM_LOGIN_2FA_CODE", raising=False)
    monkeypatch.delenv("AUTOSAHAM_LOGIN_2FA_TOTP_SECRET", raising=False)

    username = f"auth_user_{uuid.uuid4().hex[:8]}"
    _register(client, username)

    response = _login(client, username)
    assert response.status_code == 503
    assert response.json().get("detail") == "two_factor_not_configured"
