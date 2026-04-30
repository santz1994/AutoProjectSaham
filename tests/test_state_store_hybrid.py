import sqlite3

from src.api.state_store import SecureAppStateStore


class FakeRedisClient:
    def __init__(self):
        self.storage = {}

    def ping(self):
        return True

    def get(self, key):
        return self.storage.get(key)

    def set(self, key, value):
        self.storage[key] = value
        return True

    def setex(self, key, _ttl, value):
        self.storage[key] = value
        return True


class FailingRedisWriteClient(FakeRedisClient):
    def set(self, key, value):
        raise RuntimeError("redis write unavailable")

    def setex(self, key, _ttl, value):
        raise RuntimeError("redis write unavailable")


class FakePostgresClient:
    def __init__(self, *, fail_insert=False, fail_select=False, fail_count=False):
        self.logs = []
        self.fail_insert = fail_insert
        self.fail_select = fail_select
        self.fail_count = fail_count

    def execute_sql(
        self,
        statement,
        params=(),
        *,
        fetchone=False,
        fetchall=False,
    ):
        normalized = " ".join(str(statement).strip().split()).lower()

        if normalized.startswith("create table"):
            return None
        if normalized.startswith("create index"):
            return None
        if normalized == "select 1":
            return (1,) if fetchone else None

        if "insert into ai_activity_logs" in normalized:
            if self.fail_insert:
                raise RuntimeError("postgres insert unavailable")

            next_id = len(self.logs) + 1
            self.logs.append(
                {
                    "id": next_id,
                    "level": str(params[0]),
                    "event_type": str(params[1]),
                    "message": str(params[2]),
                    "payload_json": str(params[3]),
                    "created_at": str(params[4]),
                }
            )
            return (next_id,) if fetchone else None

        if "select count(1) as total from ai_activity_logs" in normalized:
            if self.fail_count:
                raise RuntimeError("postgres count unavailable")
            total = len(self.logs)
            return (total,) if fetchone else None

        if (
            "select id, level, event_type, message, payload_json, created_at"
            in normalized
        ):
            if self.fail_select:
                raise RuntimeError("postgres list unavailable")

            ordered = sorted(
                self.logs,
                key=lambda item: (item["created_at"], item["id"]),
                reverse=True,
            )
            limit = int(params[0]) if params else len(ordered)
            rows = [
                (
                    row["id"],
                    row["level"],
                    row["event_type"],
                    row["message"],
                    row["payload_json"],
                    row["created_at"],
                )
                for row in ordered[:limit]
            ]
            return rows if fetchall else None

        raise AssertionError(f"Unhandled SQL in fake postgres client: {statement}")


def _sqlite_has_secure_state_row(db_path, namespace):
    with sqlite3.connect(str(db_path)) as connection:
        row = connection.execute(
            "SELECT COUNT(1) FROM secure_state WHERE namespace = ?",
            (namespace,),
        ).fetchone()
    return int(row[0] if row else 0) > 0


def _sqlite_ai_logs_count(db_path):
    with sqlite3.connect(str(db_path)) as connection:
        row = connection.execute("SELECT COUNT(1) FROM ai_activity_logs").fetchone()
    return int(row[0] if row else 0)


def test_state_store_reads_from_redis_cache_when_sqlite_row_missing(tmp_path):
    db_path = tmp_path / "app_state.db"
    key_path = tmp_path / ".app_state.key"
    fake_redis = FakeRedisClient()

    store = SecureAppStateStore(
        db_path=str(db_path),
        key_path=str(key_path),
        redis_client=fake_redis,
        redis_prefix="autosaham:test",
    )

    payload = {"theme": "dark", "notifications": True}
    store.set_user_settings(payload)

    with sqlite3.connect(str(db_path)) as connection:
        connection.execute(
            "DELETE FROM secure_state WHERE namespace = ?",
            ("user_settings",),
        )
        connection.commit()

    restored = store.get_user_settings({"theme": "auto", "notifications": False})

    assert restored["theme"] == "dark"
    assert restored["notifications"] is True
    assert "updatedAt" in restored


def test_state_store_backfills_redis_from_sqlite_on_cache_miss(tmp_path):
    db_path = tmp_path / "app_state.db"
    key_path = tmp_path / ".app_state.key"

    sqlite_only_store = SecureAppStateStore(
        db_path=str(db_path),
        key_path=str(key_path),
    )
    sqlite_only_store.set_user_settings({"theme": "light", "notifications": False})

    fake_redis = FakeRedisClient()
    hybrid_store = SecureAppStateStore(
        db_path=str(db_path),
        key_path=str(key_path),
        redis_client=fake_redis,
        redis_prefix="autosaham:test",
    )

    loaded = hybrid_store.get_user_settings({"theme": "auto", "notifications": True})

    assert loaded["theme"] == "light"
    cache_key = "autosaham:test:secure:user_settings"
    assert fake_redis.get(cache_key)


def test_state_store_falls_back_to_sqlite_when_redis_payload_corrupt(tmp_path):
    db_path = tmp_path / "app_state.db"
    key_path = tmp_path / ".app_state.key"

    sqlite_only_store = SecureAppStateStore(
        db_path=str(db_path),
        key_path=str(key_path),
    )
    sqlite_only_store.set_user_settings({"theme": "solarized", "notifications": True})

    fake_redis = FakeRedisClient()
    hybrid_store = SecureAppStateStore(
        db_path=str(db_path),
        key_path=str(key_path),
        redis_client=fake_redis,
        redis_prefix="autosaham:test",
    )

    cache_key = "autosaham:test:secure:user_settings"
    fake_redis.set(
        cache_key,
        '{"payload":"not-a-valid-token","updated_at":"2026-01-01T00:00:00+00:00"}',
    )

    loaded = hybrid_store.get_user_settings({"theme": "auto", "notifications": False})

    assert loaded["theme"] == "solarized"
    assert loaded["notifications"] is True
    assert "not-a-valid-token" not in str(fake_redis.get(cache_key))


def test_redis_primary_namespace_prefers_redis_without_sqlite_shadow(tmp_path):
    db_path = tmp_path / "app_state.db"
    key_path = tmp_path / ".app_state.key"
    fake_redis = FakeRedisClient()

    store = SecureAppStateStore(
        db_path=str(db_path),
        key_path=str(key_path),
        redis_client=fake_redis,
        redis_prefix="autosaham:test",
        redis_primary_namespaces={"ai_regime_state"},
        redis_primary_shadow_sqlite=False,
    )

    saved = store.set_regime_state({"regime": "BULL"})

    assert saved["regime"] == "BULL"
    assert not _sqlite_has_secure_state_row(db_path, "ai_regime_state")
    assert fake_redis.get("autosaham:test:secure:ai_regime_state")


def test_redis_primary_namespace_falls_back_to_sqlite_when_redis_write_fails(tmp_path):
    db_path = tmp_path / "app_state.db"
    key_path = tmp_path / ".app_state.key"
    failing_redis = FailingRedisWriteClient()

    store = SecureAppStateStore(
        db_path=str(db_path),
        key_path=str(key_path),
        redis_client=failing_redis,
        redis_prefix="autosaham:test",
        redis_primary_namespaces={"broker_connection"},
        redis_primary_shadow_sqlite=False,
    )

    store.set_broker_connection({"provider": "stockbit", "status": "connected"})
    loaded = store.get_broker_connection({"provider": "none", "status": "disconnected"})

    assert _sqlite_has_secure_state_row(db_path, "broker_connection")
    assert loaded["provider"] == "stockbit"
    assert loaded["status"] == "connected"


def test_redis_primary_namespace_can_shadow_write_sqlite(tmp_path):
    db_path = tmp_path / "app_state.db"
    key_path = tmp_path / ".app_state.key"
    fake_redis = FakeRedisClient()

    store = SecureAppStateStore(
        db_path=str(db_path),
        key_path=str(key_path),
        redis_client=fake_redis,
        redis_prefix="autosaham:test",
        redis_primary_namespaces={"broker_connection"},
        redis_primary_shadow_sqlite=True,
    )

    store.set_broker_connection({"provider": "ajaib", "status": "connected"})

    assert _sqlite_has_secure_state_row(db_path, "broker_connection")
    assert fake_redis.get("autosaham:test:secure:broker_connection")


def test_broker_credentials_secure_namespace_roundtrip_and_clear(tmp_path):
    db_path = tmp_path / "app_state.db"
    key_path = tmp_path / ".app_state.key"

    store = SecureAppStateStore(
        db_path=str(db_path),
        key_path=str(key_path),
    )

    store.set_broker_credentials(
        {
            "provider": "indopremier",
            "accountId": "ACC-001",
            "apiKey": "test-api-key",
            "apiSecret": "test-api-secret",
        }
    )

    loaded = store.get_broker_credentials()
    assert loaded["provider"] == "indopremier"
    assert loaded["accountId"] == "ACC-001"
    assert loaded["apiKey"] == "test-api-key"
    assert loaded["apiSecret"] == "test-api-secret"
    assert _sqlite_has_secure_state_row(db_path, "broker_credentials")

    cleared = store.clear_broker_credentials()
    assert cleared["provider"] is None
    assert cleared["apiKey"] is None
    assert cleared["apiSecret"] is None


def test_migrate_secure_state_to_redis_from_sqlite(tmp_path):
    db_path = tmp_path / "app_state.db"
    key_path = tmp_path / ".app_state.key"

    sqlite_store = SecureAppStateStore(
        db_path=str(db_path),
        key_path=str(key_path),
    )
    sqlite_store.set_user_settings({"theme": "dark", "notifications": True})
    sqlite_store.set_broker_connection({"provider": "stockbit", "status": "connected"})

    fake_redis = FakeRedisClient()
    migration_store = SecureAppStateStore(
        db_path=str(db_path),
        key_path=str(key_path),
        redis_client=fake_redis,
        redis_prefix="autosaham:test",
    )

    result = migration_store.migrate_secure_state_to_redis()
    assert result["status"] == "ok"
    assert result["migrated"] >= 2
    assert fake_redis.get("autosaham:test:secure:user_settings")
    assert fake_redis.get("autosaham:test:secure:broker_connection")


def test_migrate_ai_logs_to_postgres(tmp_path):
    db_path = tmp_path / "app_state.db"
    key_path = tmp_path / ".app_state.key"

    sqlite_store = SecureAppStateStore(
        db_path=str(db_path),
        key_path=str(key_path),
    )
    sqlite_store.append_ai_log(
        level="info",
        event_type="migration",
        message="first event",
        payload={"n": 1},
        created_at="2026-04-09T00:00:00+00:00",
    )

    fake_postgres = FakePostgresClient()
    migration_store = SecureAppStateStore(
        db_path=str(db_path),
        key_path=str(key_path),
        postgres_client=fake_postgres,
        postgres_ai_logs_enabled=True,
        postgres_ai_logs_shadow_sqlite=False,
    )

    result = migration_store.migrate_ai_logs_to_postgres()
    assert result["status"] == "ok"
    assert result["migrated"] >= 1
    assert len(fake_postgres.logs) >= 1


def test_redis_primary_default_shadow_sqlite_is_enabled(tmp_path):
    db_path = tmp_path / "app_state.db"
    key_path = tmp_path / ".app_state.key"
    fake_redis = FakeRedisClient()

    store = SecureAppStateStore(
        db_path=str(db_path),
        key_path=str(key_path),
        redis_client=fake_redis,
        redis_prefix="autosaham:test",
        redis_primary_namespaces={"ai_regime_state"},
    )

    store.set_regime_state({"regime": "BEAR"})

    assert _sqlite_has_secure_state_row(db_path, "ai_regime_state")
    assert fake_redis.get("autosaham:test:secure:ai_regime_state")


def test_redis_primary_shadow_sqlite_can_be_disabled_by_env(tmp_path, monkeypatch):
    db_path = tmp_path / "app_state.db"
    key_path = tmp_path / ".app_state.key"
    fake_redis = FakeRedisClient()
    monkeypatch.setenv("AUTOSAHAM_STATE_REDIS_PRIMARY_SHADOW_SQLITE", "0")

    store = SecureAppStateStore(
        db_path=str(db_path),
        key_path=str(key_path),
        redis_client=fake_redis,
        redis_prefix="autosaham:test",
        redis_primary_namespaces={"ai_regime_state"},
    )

    store.set_regime_state({"regime": "SIDEWAYS"})

    assert not _sqlite_has_secure_state_row(db_path, "ai_regime_state")
    assert fake_redis.get("autosaham:test:secure:ai_regime_state")


def test_redis_primary_namespaces_can_be_configured_by_env(tmp_path, monkeypatch):
    db_path = tmp_path / "app_state.db"
    key_path = tmp_path / ".app_state.key"
    fake_redis = FakeRedisClient()
    monkeypatch.setenv(
        "AUTOSAHAM_STATE_REDIS_PRIMARY_NAMESPACES",
        " user_settings , ai_regime_state ",
    )
    monkeypatch.setenv("AUTOSAHAM_STATE_REDIS_PRIMARY_SHADOW_SQLITE", "0")

    store = SecureAppStateStore(
        db_path=str(db_path),
        key_path=str(key_path),
        redis_client=fake_redis,
        redis_prefix="autosaham:test",
    )

    store.set_user_settings({"theme": "dark", "notifications": True})
    store.set_broker_connection({"provider": "stockbit", "status": "connected"})

    assert not _sqlite_has_secure_state_row(db_path, "user_settings")
    assert _sqlite_has_secure_state_row(db_path, "broker_connection")


def test_system_control_roundtrip_for_kill_switch(tmp_path):
    db_path = tmp_path / "app_state.db"
    key_path = tmp_path / ".app_state.key"

    store = SecureAppStateStore(
        db_path=str(db_path),
        key_path=str(key_path),
    )

    default_state = {
        "killSwitchActive": False,
        "reason": None,
        "activatedAt": None,
        "activatedBy": None,
    }
    initial = store.get_system_control(default_state)
    assert initial["killSwitchActive"] is False

    saved = store.set_system_control(
        {
            "killSwitchActive": True,
            "reason": "unit test",
            "activatedAt": "2026-04-09T00:00:00+00:00",
            "activatedBy": "pytest",
        }
    )
    assert saved["killSwitchActive"] is True
    assert saved["reason"] == "unit test"

    loaded = store.get_system_control(default_state)
    assert loaded["killSwitchActive"] is True
    assert loaded["activatedBy"] == "pytest"


def test_ai_logs_postgres_primary_with_default_sqlite_shadow(tmp_path):
    db_path = tmp_path / "app_state.db"
    key_path = tmp_path / ".app_state.key"
    fake_postgres = FakePostgresClient()

    store = SecureAppStateStore(
        db_path=str(db_path),
        key_path=str(key_path),
        postgres_client=fake_postgres,
        postgres_ai_logs_enabled=True,
    )

    saved = store.append_ai_log(
        level="info",
        event_type="phase3",
        message="postgres primary",
        payload={"mode": "shadow"},
        created_at="2026-04-07T10:00:00+00:00",
    )

    assert saved["id"] == 1
    assert len(fake_postgres.logs) == 1
    assert _sqlite_ai_logs_count(db_path) == 1


def test_ai_logs_postgres_can_disable_sqlite_shadow(tmp_path):
    db_path = tmp_path / "app_state.db"
    key_path = tmp_path / ".app_state.key"
    fake_postgres = FakePostgresClient()

    store = SecureAppStateStore(
        db_path=str(db_path),
        key_path=str(key_path),
        postgres_client=fake_postgres,
        postgres_ai_logs_enabled=True,
        postgres_ai_logs_shadow_sqlite=False,
    )

    store.append_ai_log(
        level="info",
        event_type="phase3",
        message="postgres only",
        payload={"mode": "primary"},
        created_at="2026-04-07T10:01:00+00:00",
    )

    assert len(fake_postgres.logs) == 1
    assert _sqlite_ai_logs_count(db_path) == 0


def test_ai_logs_fallback_to_sqlite_when_postgres_insert_fails(tmp_path):
    db_path = tmp_path / "app_state.db"
    key_path = tmp_path / ".app_state.key"
    fake_postgres = FakePostgresClient(fail_insert=True)

    store = SecureAppStateStore(
        db_path=str(db_path),
        key_path=str(key_path),
        postgres_client=fake_postgres,
        postgres_ai_logs_enabled=True,
        postgres_ai_logs_shadow_sqlite=False,
    )

    saved = store.append_ai_log(
        level="warning",
        event_type="phase3",
        message="fallback sqlite",
        payload={"fallback": True},
        created_at="2026-04-07T10:02:00+00:00",
    )

    assert saved["id"] == 1
    assert len(fake_postgres.logs) == 0
    assert _sqlite_ai_logs_count(db_path) == 1


def test_list_ai_logs_prefers_postgres_and_fallbacks_to_sqlite(tmp_path):
    db_path = tmp_path / "app_state.db"
    key_path = tmp_path / ".app_state.key"

    sqlite_store = SecureAppStateStore(
        db_path=str(db_path),
        key_path=str(key_path),
    )
    sqlite_store.append_ai_log(
        level="info",
        event_type="legacy",
        message="sqlite history",
        payload={"origin": "sqlite"},
        created_at="2026-04-07T10:03:00+00:00",
    )

    fake_postgres = FakePostgresClient()
    store = SecureAppStateStore(
        db_path=str(db_path),
        key_path=str(key_path),
        postgres_client=fake_postgres,
        postgres_ai_logs_enabled=True,
        postgres_ai_logs_shadow_sqlite=False,
    )
    store.append_ai_log(
        level="info",
        event_type="primary",
        message="postgres history",
        payload={"origin": "postgres"},
        created_at="2026-04-07T10:04:00+00:00",
    )

    logs_from_postgres = store.list_ai_logs(limit=10)
    assert logs_from_postgres[0]["message"] == "postgres history"

    failing_postgres = FakePostgresClient(fail_select=True)
    fallback_store = SecureAppStateStore(
        db_path=str(db_path),
        key_path=str(key_path),
        postgres_client=failing_postgres,
        postgres_ai_logs_enabled=True,
    )

    fallback_logs = fallback_store.list_ai_logs(limit=10)
    assert any(item["message"] == "sqlite history" for item in fallback_logs)


def test_ai_logs_postgres_can_be_disabled_by_env(tmp_path, monkeypatch):
    db_path = tmp_path / "app_state.db"
    key_path = tmp_path / ".app_state.key"
    fake_postgres = FakePostgresClient()
    monkeypatch.setenv("AUTOSAHAM_STATE_POSTGRES_AI_LOGS_ENABLED", "0")

    store = SecureAppStateStore(
        db_path=str(db_path),
        key_path=str(key_path),
        postgres_client=fake_postgres,
    )

    store.append_ai_log(
        level="info",
        event_type="phase3",
        message="disabled by env",
        payload={"enabled": False},
        created_at="2026-04-07T10:05:00+00:00",
    )

    assert len(fake_postgres.logs) == 0
    assert _sqlite_ai_logs_count(db_path) == 1
