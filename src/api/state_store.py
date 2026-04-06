"""Persistent encrypted state storage for frontend settings and broker metadata.

This module stores settings and broker connection snapshots in SQLite while
encrypting secure payloads before they are written to disk.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import secrets
import sqlite3
import threading
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional

try:
    from cryptography.fernet import Fernet, InvalidToken

    FERNET_AVAILABLE = True
except Exception:  # pragma: no cover - optional dependency
    Fernet = None  # type: ignore
    InvalidToken = Exception  # type: ignore
    FERNET_AVAILABLE = False


PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
DEFAULT_DB_PATH = os.path.join(PROJECT_ROOT, "data", "app_state.db")
DEFAULT_KEY_PATH = os.path.join(PROJECT_ROOT, "data", ".app_state.key")


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _json_clone(payload: Dict[str, Any]) -> Dict[str, Any]:
    return json.loads(json.dumps(payload))


def _load_or_create_secret(key_env_var: str, key_path: str) -> str:
    env_secret = os.getenv(key_env_var, "").strip()
    if env_secret:
        return env_secret

    if os.path.exists(key_path):
        with open(key_path, "r", encoding="utf-8") as file:
            persisted = file.read().strip()
        if persisted:
            return persisted

    os.makedirs(os.path.dirname(key_path) or ".", exist_ok=True)
    generated = Fernet.generate_key().decode("utf-8") if FERNET_AVAILABLE else secrets.token_urlsafe(48)
    with open(key_path, "w", encoding="utf-8") as file:
        file.write(generated)

    try:
        os.chmod(key_path, 0o600)
    except Exception:
        # Best effort on non-POSIX filesystems.
        pass

    return generated


class _CipherProtocol:
    def encrypt_text(self, text: str) -> str:
        raise NotImplementedError

    def decrypt_text(self, token: str) -> str:
        raise NotImplementedError


class _FernetCipher(_CipherProtocol):
    def __init__(self, secret: str):
        normalized = self._normalize_key(secret)
        self._fernet = Fernet(normalized.encode("utf-8"))

    @staticmethod
    def _normalize_key(secret: str) -> str:
        candidate = secret.strip()
        try:
            decoded = base64.urlsafe_b64decode(candidate.encode("utf-8"))
            if len(decoded) == 32:
                return candidate
        except Exception:
            pass

        digest = hashlib.sha256(candidate.encode("utf-8")).digest()
        return base64.urlsafe_b64encode(digest).decode("utf-8")

    def encrypt_text(self, text: str) -> str:
        return self._fernet.encrypt(text.encode("utf-8")).decode("utf-8")

    def decrypt_text(self, token: str) -> str:
        return self._fernet.decrypt(token.encode("utf-8")).decode("utf-8")


class _XorCipher(_CipherProtocol):
    """Stdlib fallback cipher used only when cryptography is unavailable.

    This fallback keeps data obfuscated at rest, but Fernet should be preferred
    in production for authenticated encryption.
    """

    def __init__(self, secret: str):
        self._key = hashlib.sha256(secret.encode("utf-8")).digest()

    def _xor_bytes(self, data: bytes) -> bytes:
        key = self._key
        return bytes(data[index] ^ key[index % len(key)] for index in range(len(data)))

    def encrypt_text(self, text: str) -> str:
        raw = text.encode("utf-8")
        obfuscated = self._xor_bytes(raw)
        return base64.urlsafe_b64encode(obfuscated).decode("utf-8")

    def decrypt_text(self, token: str) -> str:
        obfuscated = base64.urlsafe_b64decode(token.encode("utf-8"))
        raw = self._xor_bytes(obfuscated)
        return raw.decode("utf-8")


class SecureAppStateStore:
    """SQLite-backed encrypted state store for app settings and broker metadata."""

    def __init__(
        self,
        db_path: str = DEFAULT_DB_PATH,
        key_env_var: str = "AUTOSAHAM_SETTINGS_KEY",
        key_path: str = DEFAULT_KEY_PATH,
    ):
        self.db_path = db_path
        self._lock = threading.RLock()
        os.makedirs(os.path.dirname(self.db_path) or ".", exist_ok=True)

        secret = _load_or_create_secret(key_env_var=key_env_var, key_path=key_path)
        self._cipher: _CipherProtocol = _FernetCipher(secret) if FERNET_AVAILABLE else _XorCipher(secret)

        self._ensure_schema()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        return connection

    def _ensure_schema(self) -> None:
        with self._lock:
            with self._connect() as connection:
                cursor = connection.cursor()
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS secure_state (
                        namespace TEXT PRIMARY KEY,
                        payload TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    )
                    """
                )
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS broker_feature_flags (
                        provider TEXT PRIMARY KEY,
                        live_enabled INTEGER NOT NULL DEFAULT 0,
                        paper_enabled INTEGER NOT NULL DEFAULT 1,
                        integration_ready INTEGER NOT NULL DEFAULT 0,
                        updated_at TEXT NOT NULL
                    )
                    """
                )
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS ai_activity_logs (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        level TEXT NOT NULL,
                        event_type TEXT NOT NULL,
                        message TEXT NOT NULL,
                        payload_json TEXT,
                        created_at TEXT NOT NULL
                    )
                    """
                )
                connection.commit()

    def _set_secure_payload(self, namespace: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        payload_json = json.dumps(payload, separators=(",", ":"), ensure_ascii=True)
        encrypted = self._cipher.encrypt_text(payload_json)
        now_iso = _utc_now_iso()

        with self._lock:
            with self._connect() as connection:
                cursor = connection.cursor()
                cursor.execute(
                    """
                    INSERT INTO secure_state (namespace, payload, updated_at)
                    VALUES (?, ?, ?)
                    ON CONFLICT(namespace) DO UPDATE SET
                        payload = excluded.payload,
                        updated_at = excluded.updated_at
                    """,
                    (namespace, encrypted, now_iso),
                )
                connection.commit()

        output = _json_clone(payload)
        output["updatedAt"] = now_iso
        return output

    def _get_secure_payload(self, namespace: str, default_payload: Dict[str, Any]) -> Dict[str, Any]:
        with self._lock:
            with self._connect() as connection:
                cursor = connection.cursor()
                cursor.execute(
                    "SELECT payload, updated_at FROM secure_state WHERE namespace = ?",
                    (namespace,),
                )
                row = cursor.fetchone()

        if not row:
            return self._set_secure_payload(namespace, default_payload)

        encrypted_payload = row["payload"]
        updated_at = row["updated_at"]

        try:
            decrypted_json = self._cipher.decrypt_text(encrypted_payload)
            payload = json.loads(decrypted_json)
            if isinstance(payload, dict):
                payload["updatedAt"] = updated_at
                return payload
        except (json.JSONDecodeError, ValueError, InvalidToken):
            pass
        except Exception:
            pass

        # Recovery path for corrupted payloads.
        return self._set_secure_payload(namespace, default_payload)

    def get_user_settings(self, defaults: Dict[str, Any]) -> Dict[str, Any]:
        return self._get_secure_payload("user_settings", defaults)

    def set_user_settings(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return self._set_secure_payload("user_settings", payload)

    def get_broker_connection(self, defaults: Dict[str, Any]) -> Dict[str, Any]:
        return self._get_secure_payload("broker_connection", defaults)

    def set_broker_connection(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return self._set_secure_payload("broker_connection", payload)

    def ensure_feature_flags(self, default_flags: Iterable[Dict[str, Any]]) -> None:
        now_iso = _utc_now_iso()
        with self._lock:
            with self._connect() as connection:
                cursor = connection.cursor()
                for item in default_flags:
                    provider = str(item.get("provider") or "").strip().lower()
                    if not provider:
                        continue
                    cursor.execute(
                        """
                        INSERT INTO broker_feature_flags (
                            provider,
                            live_enabled,
                            paper_enabled,
                            integration_ready,
                            updated_at
                        )
                        VALUES (?, ?, ?, ?, ?)
                        ON CONFLICT(provider) DO NOTHING
                        """,
                        (
                            provider,
                            1 if bool(item.get("liveEnabled", False)) else 0,
                            1 if bool(item.get("paperEnabled", True)) else 0,
                            1 if bool(item.get("integrationReady", False)) else 0,
                            now_iso,
                        ),
                    )
                connection.commit()

    def list_feature_flags(self) -> List[Dict[str, Any]]:
        with self._lock:
            with self._connect() as connection:
                cursor = connection.cursor()
                cursor.execute(
                    """
                    SELECT provider, live_enabled, paper_enabled, integration_ready, updated_at
                    FROM broker_feature_flags
                    ORDER BY provider ASC
                    """
                )
                rows = cursor.fetchall()

        return [
            {
                "provider": row["provider"],
                "liveEnabled": bool(row["live_enabled"]),
                "paperEnabled": bool(row["paper_enabled"]),
                "integrationReady": bool(row["integration_ready"]),
                "updatedAt": row["updated_at"],
            }
            for row in rows
        ]

    def upsert_feature_flag(
        self,
        provider: str,
        *,
        live_enabled: Optional[bool] = None,
        paper_enabled: Optional[bool] = None,
        integration_ready: Optional[bool] = None,
    ) -> Dict[str, Any]:
        normalized_provider = provider.strip().lower()
        if not normalized_provider:
            raise ValueError("provider is required")

        existing_map = {
            row["provider"]: row
            for row in self.list_feature_flags()
        }
        existing = existing_map.get(normalized_provider, {})

        merged = {
            "provider": normalized_provider,
            "liveEnabled": bool(existing.get("liveEnabled", False)),
            "paperEnabled": bool(existing.get("paperEnabled", True)),
            "integrationReady": bool(existing.get("integrationReady", False)),
            "updatedAt": _utc_now_iso(),
        }

        if live_enabled is not None:
            merged["liveEnabled"] = bool(live_enabled)
        if paper_enabled is not None:
            merged["paperEnabled"] = bool(paper_enabled)
        if integration_ready is not None:
            merged["integrationReady"] = bool(integration_ready)

        with self._lock:
            with self._connect() as connection:
                cursor = connection.cursor()
                cursor.execute(
                    """
                    INSERT INTO broker_feature_flags (
                        provider,
                        live_enabled,
                        paper_enabled,
                        integration_ready,
                        updated_at
                    )
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(provider) DO UPDATE SET
                        live_enabled = excluded.live_enabled,
                        paper_enabled = excluded.paper_enabled,
                        integration_ready = excluded.integration_ready,
                        updated_at = excluded.updated_at
                    """,
                    (
                        merged["provider"],
                        1 if merged["liveEnabled"] else 0,
                        1 if merged["paperEnabled"] else 0,
                        1 if merged["integrationReady"] else 0,
                        merged["updatedAt"],
                    ),
                )
                connection.commit()

        return merged

    def append_ai_log(
        self,
        *,
        level: str,
        event_type: str,
        message: str,
        payload: Optional[Dict[str, Any]] = None,
        created_at: Optional[str] = None,
    ) -> Dict[str, Any]:
        created = created_at or _utc_now_iso()
        payload_json = json.dumps(payload or {}, ensure_ascii=True)

        with self._lock:
            with self._connect() as connection:
                cursor = connection.cursor()
                cursor.execute(
                    """
                    INSERT INTO ai_activity_logs (level, event_type, message, payload_json, created_at)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (level, event_type, message, payload_json, created),
                )
                inserted_id = cursor.lastrowid
                connection.commit()

        return {
            "id": int(inserted_id or 0),
            "level": level,
            "eventType": event_type,
            "message": message,
            "payload": payload or {},
            "timestamp": created,
        }

    def ensure_seed_ai_logs(self, seed_logs: Iterable[Dict[str, Any]]) -> None:
        with self._lock:
            with self._connect() as connection:
                cursor = connection.cursor()
                cursor.execute("SELECT COUNT(1) AS total FROM ai_activity_logs")
                row = cursor.fetchone()
                total = int(row["total"]) if row else 0

        if total > 0:
            return

        for item in seed_logs:
            self.append_ai_log(
                level=str(item.get("level", "info")),
                event_type=str(item.get("eventType", "system")),
                message=str(item.get("message", "AI event")),
                payload=item.get("payload", {}),
                created_at=item.get("timestamp"),
            )

    def list_ai_logs(self, limit: int = 100) -> List[Dict[str, Any]]:
        safe_limit = max(1, min(int(limit or 100), 500))
        with self._lock:
            with self._connect() as connection:
                cursor = connection.cursor()
                cursor.execute(
                    """
                    SELECT id, level, event_type, message, payload_json, created_at
                    FROM ai_activity_logs
                    ORDER BY created_at DESC, id DESC
                    LIMIT ?
                    """,
                    (safe_limit,),
                )
                rows = cursor.fetchall()

        logs: List[Dict[str, Any]] = []
        for row in rows:
            payload_json = row["payload_json"]
            try:
                payload = json.loads(payload_json) if payload_json else {}
            except json.JSONDecodeError:
                payload = {}

            logs.append(
                {
                    "id": int(row["id"]),
                    "level": row["level"],
                    "eventType": row["event_type"],
                    "message": row["message"],
                    "payload": payload,
                    "timestamp": row["created_at"],
                }
            )

        return logs
