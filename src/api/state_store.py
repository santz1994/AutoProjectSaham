"""Persistent encrypted state storage for frontend and runtime metadata.

This module uses SQLite as durable fallback storage, with optional Redis
primary routing for selected secure namespaces and optional PostgreSQL primary
routing for AI activity logs.
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
from typing import Any, Dict, Iterable, List, Optional, Tuple

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


def _resolve_redis_url(explicit_url: Optional[str] = None) -> Optional[str]:
    candidates = [
        explicit_url,
        os.getenv("AUTOSAHAM_STATE_REDIS_URL"),
        os.getenv("REDIS_URL"),
        os.getenv("CELERY_BROKER_URL"),
    ]
    for item in candidates:
        candidate = str(item or "").strip()
        if candidate.lower().startswith(("redis://", "rediss://")):
            return candidate
    return None


def _resolve_postgres_url(explicit_url: Optional[str] = None) -> Optional[str]:
    candidates = [
        explicit_url,
        os.getenv("AUTOSAHAM_STATE_POSTGRES_URL"),
        os.getenv("DATABASE_URL"),
    ]
    for item in candidates:
        candidate = str(item or "").strip()
        if candidate.lower().startswith(("postgres://", "postgresql://")):
            return candidate
    return None


def _env_bool(value: Optional[str], default: bool) -> bool:
    if value is None:
        return default

    normalized = str(value).strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    return default


def _normalize_namespace_set(namespaces: Iterable[str]) -> set[str]:
    normalized: set[str] = set()
    for item in namespaces:
        candidate = str(item or "").strip().lower()
        if candidate:
            normalized.add(candidate)
    return normalized


def _resolve_primary_namespaces(
    explicit_namespaces: Optional[Iterable[str]] = None,
) -> set[str]:
    if explicit_namespaces is not None:
        return _normalize_namespace_set(explicit_namespaces)

    configured = os.getenv(
        "AUTOSAHAM_STATE_REDIS_PRIMARY_NAMESPACES",
        "ai_regime_state,broker_connection,user_settings",
    )
    return _normalize_namespace_set(configured.split(","))


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


class _PostgresClientAdapter:
    def __init__(self, connection: Any):
        self._connection = connection

    def execute_sql(
        self,
        statement: str,
        params: Tuple[Any, ...] = (),
        *,
        fetchone: bool = False,
        fetchall: bool = False,
    ) -> Any:
        with self._connection.cursor() as cursor:
            cursor.execute(statement, params)
            if fetchone:
                return cursor.fetchone()
            if fetchall:
                return cursor.fetchall()
        return None


class SecureAppStateStore:
    """Encrypted app state store with Redis cache and SQLite fallback support."""

    def __init__(
        self,
        db_path: str = DEFAULT_DB_PATH,
        key_env_var: str = "AUTOSAHAM_SETTINGS_KEY",
        key_path: str = DEFAULT_KEY_PATH,
        redis_client: Optional[Any] = None,
        redis_url: Optional[str] = None,
        redis_prefix: str = "autosaham:state",
        redis_primary_namespaces: Optional[Iterable[str]] = None,
        redis_primary_shadow_sqlite: Optional[bool] = None,
        postgres_client: Optional[Any] = None,
        postgres_url: Optional[str] = None,
        postgres_ai_logs_enabled: Optional[bool] = None,
        postgres_ai_logs_shadow_sqlite: Optional[bool] = None,
    ):
        self.db_path = db_path
        self._lock = threading.RLock()
        os.makedirs(os.path.dirname(self.db_path) or ".", exist_ok=True)

        secret = _load_or_create_secret(key_env_var=key_env_var, key_path=key_path)
        self._cipher: _CipherProtocol = (
            _FernetCipher(secret) if FERNET_AVAILABLE else _XorCipher(secret)
        )
        safe_prefix = str(redis_prefix or "autosaham:state").strip().strip(":")
        self._redis_prefix = safe_prefix or "autosaham:state"
        self._redis_client = (
            redis_client
            if redis_client is not None
            else self._init_redis_client(redis_url)
        )
        self._redis_primary_namespaces = _resolve_primary_namespaces(
            redis_primary_namespaces
        )

        if redis_primary_shadow_sqlite is None:
            redis_primary_shadow_sqlite = _env_bool(
                os.getenv("AUTOSAHAM_STATE_REDIS_PRIMARY_SHADOW_SQLITE"),
                True,
            )
        self._redis_primary_shadow_sqlite = bool(redis_primary_shadow_sqlite)

        self._postgres_client = (
            postgres_client
            if postgres_client is not None
            else self._init_postgres_client(postgres_url)
        )
        if postgres_ai_logs_enabled is None:
            postgres_ai_logs_enabled = _env_bool(
                os.getenv("AUTOSAHAM_STATE_POSTGRES_AI_LOGS_ENABLED"),
                True,
            )
        self._postgres_ai_logs_enabled = bool(postgres_ai_logs_enabled)

        if postgres_ai_logs_shadow_sqlite is None:
            postgres_ai_logs_shadow_sqlite = _env_bool(
                os.getenv("AUTOSAHAM_STATE_POSTGRES_AI_LOGS_SHADOW_SQLITE"),
                True,
            )
        self._postgres_ai_logs_shadow_sqlite = bool(postgres_ai_logs_shadow_sqlite)

        self._ensure_schema()

    def _is_redis_primary_namespace(self, namespace: str) -> bool:
        normalized = str(namespace or "").strip().lower()
        return normalized in self._redis_primary_namespaces

    def _init_redis_client(self, redis_url: Optional[str]) -> Optional[Any]:
        resolved_url = _resolve_redis_url(redis_url)
        if not resolved_url:
            return None

        try:
            import redis
        except Exception:
            return None

        try:
            client = redis.Redis.from_url(
                resolved_url,
                decode_responses=True,
                socket_connect_timeout=0.5,
                socket_timeout=0.5,
            )
            client.ping()
            return client
        except Exception:
            return None

    def _init_postgres_client(self, postgres_url: Optional[str]) -> Optional[Any]:
        resolved_url = _resolve_postgres_url(postgres_url)
        if not resolved_url:
            return None

        try:
            import psycopg
        except Exception:
            return None

        try:
            connection = psycopg.connect(
                resolved_url,
                connect_timeout=1,
                autocommit=True,
            )
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
            return _PostgresClientAdapter(connection)
        except Exception:
            return None

    def _postgres_execute_sql(
        self,
        statement: str,
        params: Tuple[Any, ...] = (),
        *,
        fetchone: bool = False,
        fetchall: bool = False,
    ) -> Any:
        if not self._postgres_ai_logs_enabled:
            return None
        if self._postgres_client is None:
            return None

        try:
            return self._postgres_client.execute_sql(
                statement,
                params,
                fetchone=fetchone,
                fetchall=fetchall,
            )
        except Exception:
            return None

    def _ensure_postgres_schema(self) -> None:
        self._postgres_execute_sql(
            """
            CREATE TABLE IF NOT EXISTS ai_activity_logs (
                id BIGSERIAL PRIMARY KEY,
                level TEXT NOT NULL,
                event_type TEXT NOT NULL,
                message TEXT NOT NULL,
                payload_json TEXT,
                created_at TIMESTAMPTZ NOT NULL
            )
            """
        )
        self._postgres_execute_sql(
            """
            CREATE INDEX IF NOT EXISTS idx_ai_activity_logs_created_at
            ON ai_activity_logs (created_at DESC, id DESC)
            """
        )

    def _redis_secure_key(self, namespace: str) -> str:
        return f"{self._redis_prefix}:secure:{namespace}"

    def _redis_read_secure_payload(self, namespace: str) -> Optional[Tuple[str, str]]:
        if self._redis_client is None:
            return None

        try:
            raw_value = self._redis_client.get(self._redis_secure_key(namespace))
            if not raw_value:
                return None

            payload = json.loads(str(raw_value))
            encrypted_payload = str(payload.get("payload") or "").strip()
            updated_at = str(payload.get("updated_at") or "").strip()
            if not encrypted_payload or not updated_at:
                return None

            return encrypted_payload, updated_at
        except Exception:
            return None

    def _redis_write_secure_payload(
        self,
        namespace: str,
        encrypted_payload: str,
        updated_at: str,
    ) -> bool:
        if self._redis_client is None:
            return False

        serialized = json.dumps(
            {
                "payload": encrypted_payload,
                "updated_at": updated_at,
            },
            separators=(",", ":"),
            ensure_ascii=True,
        )
        ttl_seconds = int(os.getenv("AUTOSAHAM_STATE_REDIS_TTL_SECONDS", "0") or 0)

        try:
            if ttl_seconds > 0:
                self._redis_client.setex(
                    self._redis_secure_key(namespace),
                    ttl_seconds,
                    serialized,
                )
            else:
                self._redis_client.set(self._redis_secure_key(namespace), serialized)
            return True
        except Exception:
            return False

    def _sqlite_write_secure_payload(
        self,
        namespace: str,
        encrypted_payload: str,
        updated_at: str,
    ) -> None:
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
                    (namespace, encrypted_payload, updated_at),
                )
                connection.commit()

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

        self._ensure_postgres_schema()

    def _row_value(self, row: Any, key: str, index: int) -> Any:
        try:
            return row[key]
        except Exception:
            pass
        try:
            return row[index]
        except Exception:
            return None

    def _parse_payload_json(self, payload_json: Any) -> Dict[str, Any]:
        if payload_json in (None, ""):
            return {}
        try:
            payload = json.loads(str(payload_json))
            return payload if isinstance(payload, dict) else {}
        except Exception:
            return {}

    def _format_ai_log(self, row: Any) -> Dict[str, Any]:
        return {
            "id": int(self._row_value(row, "id", 0) or 0),
            "level": str(self._row_value(row, "level", 1) or "info"),
            "eventType": str(self._row_value(row, "event_type", 2) or "system"),
            "message": str(self._row_value(row, "message", 3) or "AI event"),
            "payload": self._parse_payload_json(self._row_value(row, "payload_json", 4)),
            "timestamp": str(self._row_value(row, "created_at", 5) or _utc_now_iso()),
        }

    def _insert_ai_log_sqlite(
        self,
        *,
        level: str,
        event_type: str,
        message: str,
        payload_json: str,
        created_at: str,
    ) -> int:
        with self._lock:
            with self._connect() as connection:
                cursor = connection.cursor()
                cursor.execute(
                    """
                    INSERT INTO ai_activity_logs (level, event_type, message, payload_json, created_at)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (level, event_type, message, payload_json, created_at),
                )
                inserted_id = int(cursor.lastrowid or 0)
                connection.commit()
        return inserted_id

    def _insert_ai_log_postgres(
        self,
        *,
        level: str,
        event_type: str,
        message: str,
        payload_json: str,
        created_at: str,
    ) -> Optional[int]:
        row = self._postgres_execute_sql(
            """
            INSERT INTO ai_activity_logs (level, event_type, message, payload_json, created_at)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id
            """,
            (level, event_type, message, payload_json, created_at),
            fetchone=True,
        )
        if row is None:
            return None
        inserted_id = self._row_value(row, "id", 0)
        try:
            return int(inserted_id)
        except Exception:
            return None

    def _count_ai_logs_sqlite(self) -> int:
        with self._lock:
            with self._connect() as connection:
                cursor = connection.cursor()
                cursor.execute("SELECT COUNT(1) AS total FROM ai_activity_logs")
                row = cursor.fetchone()
                return int(row["total"]) if row else 0

    def _count_ai_logs_postgres(self) -> Optional[int]:
        row = self._postgres_execute_sql(
            "SELECT COUNT(1) AS total FROM ai_activity_logs",
            fetchone=True,
        )
        if row is None:
            return None
        value = self._row_value(row, "total", 0)
        try:
            return int(value)
        except Exception:
            return None

    def _list_ai_logs_sqlite(self, limit: int) -> List[Dict[str, Any]]:
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
                    (limit,),
                )
                rows = cursor.fetchall()

        return [self._format_ai_log(row) for row in rows]

    def _list_ai_logs_postgres(self, limit: int) -> Optional[List[Dict[str, Any]]]:
        rows = self._postgres_execute_sql(
            """
            SELECT id, level, event_type, message, payload_json, created_at
            FROM ai_activity_logs
            ORDER BY created_at DESC, id DESC
            LIMIT %s
            """,
            (limit,),
            fetchall=True,
        )
        if rows is None:
            return None
        return [self._format_ai_log(row) for row in rows]

    def _set_secure_payload(
        self,
        namespace: str,
        payload: Dict[str, Any],
    ) -> Dict[str, Any]:
        payload_json = json.dumps(payload, separators=(",", ":"), ensure_ascii=True)
        encrypted = self._cipher.encrypt_text(payload_json)
        now_iso = _utc_now_iso()

        if self._is_redis_primary_namespace(namespace):
            redis_written = self._redis_write_secure_payload(
                namespace,
                encrypted,
                now_iso,
            )
            if self._redis_primary_shadow_sqlite or not redis_written:
                self._sqlite_write_secure_payload(namespace, encrypted, now_iso)
        else:
            self._sqlite_write_secure_payload(namespace, encrypted, now_iso)
            self._redis_write_secure_payload(namespace, encrypted, now_iso)

        output = _json_clone(payload)
        output["updatedAt"] = now_iso
        return output

    def _get_secure_payload(
        self,
        namespace: str,
        default_payload: Dict[str, Any],
    ) -> Dict[str, Any]:
        redis_cached = self._redis_read_secure_payload(namespace)
        if redis_cached:
            cached_encrypted_payload, cached_updated_at = redis_cached
            try:
                decrypted_json = self._cipher.decrypt_text(cached_encrypted_payload)
                payload = json.loads(decrypted_json)
                if isinstance(payload, dict):
                    payload["updatedAt"] = cached_updated_at
                    return payload
            except (json.JSONDecodeError, ValueError, InvalidToken):
                pass
            except Exception:
                pass

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
                self._redis_write_secure_payload(
                    namespace,
                    encrypted_payload,
                    updated_at,
                )
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

    def get_broker_credentials(
        self,
        defaults: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        default_payload = defaults or {
            "provider": None,
            "accountId": None,
            "apiKey": None,
            "apiSecret": None,
        }
        return self._get_secure_payload("broker_credentials", default_payload)

    def set_broker_credentials(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return self._set_secure_payload("broker_credentials", payload)

    def clear_broker_credentials(self) -> Dict[str, Any]:
        return self._set_secure_payload(
            "broker_credentials",
            {
                "provider": None,
                "accountId": None,
                "apiKey": None,
                "apiSecret": None,
            },
        )

    def get_regime_state(self, defaults: Dict[str, Any]) -> Dict[str, Any]:
        return self._get_secure_payload("ai_regime_state", defaults)

    def set_regime_state(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return self._set_secure_payload("ai_regime_state", payload)

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

    def get_state_migration_status(self) -> Dict[str, Any]:
        with self._lock:
            with self._connect() as connection:
                cursor = connection.cursor()
                cursor.execute(
                    "SELECT namespace, updated_at FROM secure_state ORDER BY namespace"
                )
                secure_rows = cursor.fetchall()
                cursor.execute("SELECT COUNT(1) AS total FROM ai_activity_logs")
                sqlite_ai_logs_row = cursor.fetchone()

        secure_namespaces = [str(row["namespace"]) for row in secure_rows]
        redis_cached = 0
        for namespace in secure_namespaces:
            if self._redis_read_secure_payload(namespace):
                redis_cached += 1

        postgres_ai_logs = self._count_ai_logs_postgres()

        return {
            "secureState": {
                "sqliteCount": len(secure_rows),
                "redisCachedCount": redis_cached,
                "namespaces": secure_namespaces,
                "redisPrimaryNamespaces": sorted(list(self._redis_primary_namespaces)),
                "redisPrimaryShadowSqlite": bool(self._redis_primary_shadow_sqlite),
                "redisAvailable": self._redis_client is not None,
            },
            "aiLogs": {
                "sqliteCount": int(sqlite_ai_logs_row["total"]) if sqlite_ai_logs_row else 0,
                "postgresCount": postgres_ai_logs,
                "postgresEnabled": bool(self._postgres_ai_logs_enabled),
                "postgresAvailable": self._postgres_client is not None,
                "postgresShadowSqlite": bool(self._postgres_ai_logs_shadow_sqlite),
            },
        }

    def migrate_secure_state_to_redis(
        self,
        namespaces: Optional[Iterable[str]] = None,
        *,
        clear_sqlite: bool = False,
    ) -> Dict[str, Any]:
        if self._redis_client is None:
            return {
                "status": "skipped",
                "reason": "redis_unavailable",
                "processed": 0,
                "migrated": 0,
                "deletedFromSqlite": 0,
            }

        if namespaces is None:
            target_namespaces = None
        else:
            target_namespaces = {
                str(item or "").strip().lower()
                for item in namespaces
                if str(item or "").strip()
            }

        with self._lock:
            with self._connect() as connection:
                cursor = connection.cursor()
                cursor.execute(
                    "SELECT namespace, payload, updated_at FROM secure_state ORDER BY namespace"
                )
                rows = cursor.fetchall()

                processed = 0
                migrated = 0
                deleted = 0

                for row in rows:
                    namespace = str(row["namespace"] or "").strip().lower()
                    if not namespace:
                        continue
                    if target_namespaces is not None and namespace not in target_namespaces:
                        continue

                    processed += 1
                    written = self._redis_write_secure_payload(
                        namespace,
                        str(row["payload"] or ""),
                        str(row["updated_at"] or _utc_now_iso()),
                    )
                    if not written:
                        continue
                    migrated += 1

                    if clear_sqlite:
                        cursor.execute(
                            "DELETE FROM secure_state WHERE namespace = ?",
                            (namespace,),
                        )
                        deleted += int(cursor.rowcount or 0)

                if clear_sqlite:
                    connection.commit()

        return {
            "status": "ok",
            "processed": processed,
            "migrated": migrated,
            "deletedFromSqlite": deleted,
            "clearSqlite": bool(clear_sqlite),
        }

    def _postgres_ai_log_exists(
        self,
        *,
        event_type: str,
        message: str,
        created_at: str,
    ) -> bool:
        row = self._postgres_execute_sql(
            """
            SELECT id
            FROM ai_activity_logs
            WHERE event_type = %s AND message = %s AND created_at = %s
            LIMIT 1
            """,
            (event_type, message, created_at),
            fetchone=True,
        )
        return row is not None

    def migrate_ai_logs_to_postgres(
        self,
        *,
        clear_sqlite: bool = False,
        limit: int = 20000,
    ) -> Dict[str, Any]:
        if not self._postgres_ai_logs_enabled or self._postgres_client is None:
            return {
                "status": "skipped",
                "reason": "postgres_unavailable",
                "processed": 0,
                "migrated": 0,
                "duplicates": 0,
                "deletedFromSqlite": 0,
            }

        with self._lock:
            with self._connect() as connection:
                cursor = connection.cursor()
                cursor.execute(
                    """
                    SELECT id, level, event_type, message, payload_json, created_at
                    FROM ai_activity_logs
                    ORDER BY id ASC
                    LIMIT ?
                    """,
                    (max(1, int(limit)),),
                )
                rows = cursor.fetchall()

                processed = 0
                migrated = 0
                duplicates = 0
                deleted = 0

                for row in rows:
                    processed += 1
                    level = str(row["level"] or "info")
                    event_type = str(row["event_type"] or "system")
                    message = str(row["message"] or "AI event")
                    payload_json = str(row["payload_json"] or "{}")
                    created_at = str(row["created_at"] or _utc_now_iso())

                    if self._postgres_ai_log_exists(
                        event_type=event_type,
                        message=message,
                        created_at=created_at,
                    ):
                        duplicates += 1
                        if clear_sqlite:
                            cursor.execute(
                                "DELETE FROM ai_activity_logs WHERE id = ?",
                                (int(row["id"]),),
                            )
                            deleted += int(cursor.rowcount or 0)
                        continue

                    inserted = self._insert_ai_log_postgres(
                        level=level,
                        event_type=event_type,
                        message=message,
                        payload_json=payload_json,
                        created_at=created_at,
                    )
                    if inserted is None:
                        continue

                    migrated += 1
                    if clear_sqlite:
                        cursor.execute(
                            "DELETE FROM ai_activity_logs WHERE id = ?",
                            (int(row["id"]),),
                        )
                        deleted += int(cursor.rowcount or 0)

                if clear_sqlite:
                    connection.commit()

        return {
            "status": "ok",
            "processed": processed,
            "migrated": migrated,
            "duplicates": duplicates,
            "deletedFromSqlite": deleted,
            "clearSqlite": bool(clear_sqlite),
        }

    def run_state_backend_migration(
        self,
        *,
        clear_sqlite: bool = False,
    ) -> Dict[str, Any]:
        secure_result = self.migrate_secure_state_to_redis(
            clear_sqlite=clear_sqlite
        )
        ai_logs_result = self.migrate_ai_logs_to_postgres(
            clear_sqlite=clear_sqlite
        )
        return {
            "status": "ok",
            "clearSqlite": bool(clear_sqlite),
            "secureState": secure_result,
            "aiLogs": ai_logs_result,
            "postMigration": self.get_state_migration_status(),
        }

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

        postgres_inserted_id = self._insert_ai_log_postgres(
            level=level,
            event_type=event_type,
            message=message,
            payload_json=payload_json,
            created_at=created,
        )

        sqlite_inserted_id: Optional[int] = None
        if self._postgres_ai_logs_shadow_sqlite or postgres_inserted_id is None:
            sqlite_inserted_id = self._insert_ai_log_sqlite(
                level=level,
                event_type=event_type,
                message=message,
                payload_json=payload_json,
                created_at=created,
            )

        inserted_id = postgres_inserted_id
        if inserted_id is None:
            inserted_id = sqlite_inserted_id

        return {
            "id": int(inserted_id or 0),
            "level": level,
            "eventType": event_type,
            "message": message,
            "payload": payload or {},
            "timestamp": created,
        }

    def ensure_seed_ai_logs(self, seed_logs: Iterable[Dict[str, Any]]) -> None:
        total = self._count_ai_logs_postgres()
        if total is None:
            total = self._count_ai_logs_sqlite()

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
        postgres_logs = self._list_ai_logs_postgres(safe_limit)
        if postgres_logs:
            return postgres_logs
        if postgres_logs == []:
            sqlite_logs = self._list_ai_logs_sqlite(safe_limit)
            return sqlite_logs if sqlite_logs else postgres_logs
        return self._list_ai_logs_sqlite(safe_limit)
