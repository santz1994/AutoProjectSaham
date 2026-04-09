"""Authentication helpers for local/runtime deployments.

This module provides a filesystem-backed user registry and in-memory session
and password-reset token storage. For internet-facing production, use a proper
database-backed identity provider and external reset email delivery.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import secrets
import time
from typing import Any, Dict, Optional

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
_USERS_FILE = os.path.join(PROJECT_ROOT, "data", "users.json")
_SESSIONS: Dict[str, Dict[str, Any]] = {}
_RESET_TOKENS: Dict[str, Dict[str, Any]] = {}
_DEFAULT_ROLE = "trader"
_VALID_ROLES = {"admin", "trader", "viewer", "developer"}


def _ensure_users_file() -> None:
    os.makedirs(os.path.dirname(_USERS_FILE), exist_ok=True)
    if not os.path.exists(_USERS_FILE):
        with open(_USERS_FILE, "w", encoding="utf8") as fh:
            json.dump({}, fh)


def _normalize_role(value: Any, username: Optional[str] = None) -> str:
    normalized = str(value or "").strip().lower()
    if normalized in _VALID_ROLES:
        return normalized

    if str(username or "").strip().lower() == "admin":
        return "admin"

    return _DEFAULT_ROLE


def _normalize_user_record(payload: Any, username: Optional[str] = None) -> Dict[str, Any]:
    if isinstance(payload, str):
        return {
            "password": payload,
            "email": None,
            "createdAt": None,
            "role": _normalize_role(None, username=username),
        }

    if isinstance(payload, dict):
        password = str(payload.get("password") or payload.get("passwordHash") or "").strip()
        email = str(payload.get("email") or "").strip().lower() or None
        created_at = str(payload.get("createdAt") or "").strip() or None
        role = _normalize_role(payload.get("role"), username=username)
        return {
            "password": password,
            "email": email,
            "createdAt": created_at,
            "role": role,
        }

    return {
        "password": "",
        "email": None,
        "createdAt": None,
        "role": _normalize_role(None, username=username),
    }


def _is_valid_email(email: str) -> bool:
    candidate = str(email or "").strip()
    if "@" not in candidate:
        return False
    local_part, _, domain = candidate.partition("@")
    return bool(local_part and domain and "." in domain)


def _find_username_by_email(users: Dict[str, Dict[str, Any]], email: str) -> Optional[str]:
    normalized_email = str(email or "").strip().lower()
    if not normalized_email:
        return None

    for username, record in users.items():
        if str(record.get("email") or "").strip().lower() == normalized_email:
            return username
    return None


def _load_users() -> Dict[str, Dict[str, Any]]:
    _ensure_users_file()
    with open(_USERS_FILE, "r", encoding="utf8") as fh:
        try:
            raw_payload = json.load(fh)
        except Exception:
            return {}

    if not isinstance(raw_payload, dict):
        return {}

    users: Dict[str, Dict[str, Any]] = {}
    for raw_username, raw_record in raw_payload.items():
        username = str(raw_username or "").strip()
        if not username:
            continue
        normalized = _normalize_user_record(raw_record, username=username)
        if not normalized.get("password"):
            continue
        users[username] = normalized

    return users


def _save_users(users: Dict[str, Dict[str, Any]]) -> None:
    _ensure_users_file()
    serialized = {
        username: {
            "password": str(record.get("password") or ""),
            "email": str(record.get("email") or "").strip().lower() or None,
            "createdAt": str(record.get("createdAt") or "").strip() or None,
            "role": _normalize_role(record.get("role"), username=username),
        }
        for username, record in users.items()
    }
    with open(_USERS_FILE, "w", encoding="utf8") as fh:
        json.dump(serialized, fh, indent=2)


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


def register_user(
    username: str,
    password: str,
    email: Optional[str] = None,
    role: Optional[str] = None,
) -> None:
    normalized_username = str(username or "").strip()
    normalized_password = str(password or "")
    normalized_email = str(email or "").strip().lower() or None

    if len(normalized_username) < 3:
        raise RuntimeError("username_too_short")
    if len(normalized_password) < 6:
        raise RuntimeError("password_too_short")
    if normalized_email and not _is_valid_email(normalized_email):
        raise RuntimeError("invalid_email")

    users = _load_users()
    if normalized_username in users:
        raise RuntimeError("user exists")

    if normalized_email and _find_username_by_email(users, normalized_email):
        raise RuntimeError("email_exists")

    users[normalized_username] = {
        "password": _hash_password(normalized_password),
        "email": normalized_email,
        "createdAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "role": _normalize_role(role, username=normalized_username),
    }
    _save_users(users)


def get_user_role(username: str) -> str:
    normalized_username = str(username or "").strip()
    if not normalized_username:
        return _DEFAULT_ROLE

    users = _load_users()
    user_record = users.get(normalized_username) or {}
    return _normalize_role(user_record.get("role"), username=normalized_username)


def authenticate_user(username: str, password: str, ttl_seconds: int = 3600 * 24) -> Optional[str]:
    users = _load_users()
    user_record = users.get(username)
    if not user_record:
        return None
    stored_hash = str(user_record.get("password") or "")
    if not stored_hash:
        return None
    if not _verify_password(password, stored_hash):
        return None

    role = _normalize_role(user_record.get("role"), username=username)
    csrf_token = secrets.token_urlsafe(24)
    token = secrets.token_urlsafe(32)
    _SESSIONS[token] = {
        "username": username,
        "role": role,
        "csrf_token": csrf_token,
        "issued_at": time.time(),
        "expires_at": time.time() + float(ttl_seconds),
    }
    return token


def request_password_reset(email: str, ttl_seconds: int = 15 * 60) -> Optional[str]:
    normalized_email = str(email or "").strip().lower()
    if not _is_valid_email(normalized_email):
        return None

    users = _load_users()
    username = _find_username_by_email(users, normalized_email)
    if not username:
        return None

    reset_token = secrets.token_urlsafe(32)
    _RESET_TOKENS[reset_token] = {
        "username": username,
        "expires_at": time.time() + float(ttl_seconds),
    }
    return reset_token


def reset_password(reset_token: str, new_password: str) -> bool:
    token = str(reset_token or "").strip()
    password = str(new_password or "")

    if len(token) < 10:
        return False
    if len(password) < 6:
        return False

    reset_session = _RESET_TOKENS.get(token)
    if not reset_session:
        return False

    if float(reset_session.get("expires_at") or 0.0) < time.time():
        _RESET_TOKENS.pop(token, None)
        return False

    username = str(reset_session.get("username") or "").strip()
    if not username:
        _RESET_TOKENS.pop(token, None)
        return False

    users = _load_users()
    user_record = users.get(username)
    if not user_record:
        _RESET_TOKENS.pop(token, None)
        return False

    users[username] = {
        **user_record,
        "password": _hash_password(password),
    }
    _save_users(users)
    _RESET_TOKENS.pop(token, None)
    return True


def get_session_context(token: str) -> Optional[Dict[str, Any]]:
    s = _SESSIONS.get(token)
    if not s:
        return None
    if s.get("expires_at", 0) < time.time():
        _SESSIONS.pop(token, None)
        return None

    username = str(s.get("username") or "").strip()
    role = _normalize_role(s.get("role"), username=username)
    csrf_token = str(s.get("csrf_token") or "").strip()

    # Backfill older sessions created before role/csrf fields were introduced.
    if username and not str(s.get("role") or "").strip():
        s["role"] = role
    if username and not csrf_token:
        csrf_token = secrets.token_urlsafe(24)
        s["csrf_token"] = csrf_token

    return {
        "username": username,
        "role": role,
        "csrfToken": csrf_token,
        "expiresAt": float(s.get("expires_at") or 0.0),
    }


def get_user_from_token(token: str) -> Optional[str]:
    context = get_session_context(token)
    if not context:
        return None
    return str(context.get("username") or "").strip() or None


def invalidate_token(token: str) -> bool:
    return _SESSIONS.pop(token, None) is not None
