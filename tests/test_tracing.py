from src.monitoring.tracing import get_tracer, init_tracing, reset_tracing_for_tests


def setup_function():
    reset_tracing_for_tests()


def test_tracing_disabled_by_default(monkeypatch):
    monkeypatch.delenv("AUTOSAHAM_TRACING_ENABLED", raising=False)

    enabled = init_tracing(service_name="autosaham-test")

    assert enabled is False
    assert get_tracer() is None


def test_tracing_disabled_explicit_flag(monkeypatch):
    monkeypatch.setenv("AUTOSAHAM_TRACING_ENABLED", "0")

    enabled = init_tracing(service_name="autosaham-test")

    assert enabled is False
    assert get_tracer() is None
