"""Simple authentication helpers for demo purposes.

This module provides a tiny username/password registry and token sessions.
It's suitable for local demos. For production use OAuth2 / JWT and a proper
user database + secure storage.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import secrets
import time
from typing import Optional

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
_USERS_FILE = os.path.join(PROJECT_ROOT, "data", "users.json")
_SESSIONS: dict = {}  # token -> {username, expires_at}


def _ensure_users_file() -> None:
    os.makedirs(os.path.dirname(_USERS_FILE), exist_ok=True)
    if not os.path.exists(_USERS_FILE):
        with open(_USERS_FILE, "w", encoding="utf8") as fh:
            json.dump({}, fh)


def _load_users() -> dict:
    _ensure_users_file()
    with open(_USERS_FILE, "r", encoding="utf8") as fh:
        try:
            return json.load(fh)
        except Exception:
            return {}


def _save_users(users: dict) -> None:
    _ensure_users_file()
    with open(_USERS_FILE, "w", encoding="utf8") as fh:
        json.dump(users, fh, indent=2)


def _hash_password(password: str, salt: Optional[str] = None) -> str:
    if salt is None:
        salt = secrets.token_hex(16)
    key = hashlib.pbkdf2_hmac("sha256", password.encode("utf8"), salt.encode("utf8"), 100_000)
    return salt + "$" + base64.b64encode(key).decode("ascii")


def _verify_password(password: str, stored: str) -> bool:
    try:
        salt, b64 = stored.split("$", 1)
    except Exception:
        return False
    calc = hashlib.pbkdf2_hmac("sha256", password.encode("utf8"), salt.encode("utf8"), 100_000)
    return base64.b64encode(calc).decode("ascii") == b64


def register_user(username: str, password: str) -> None:
    users = _load_users()
    if username in users:
        raise RuntimeError("user exists")
    users[username] = _hash_password(password)
    _save_users(users)


def authenticate_user(username: str, password: str, ttl_seconds: int = 3600 * 24) -> Optional[str]:
    users = _load_users()
    stored = users.get(username)
    if not stored:
        return None
    if not _verify_password(password, stored):
        return None
    token = secrets.token_urlsafe(32)
    _SESSIONS[token] = {"username": username, "expires_at": time.time() + float(ttl_seconds)}
    return token


def get_user_from_token(token: str) -> Optional[str]:
    s = _SESSIONS.get(token)
    if not s:
        return None
    if s.get("expires_at", 0) < time.time():
        _SESSIONS.pop(token, None)
        return None
    return s.get("username")


def invalidate_token(token: str) -> bool:
    return _SESSIONS.pop(token, None) is not None
