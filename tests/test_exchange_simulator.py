from src.execution.exchange_simulator import (
    LocalExchangeSimulator,
    OrderIntent,
    SimulationConfig,
)


def test_simulator_latency_within_bounds():
    cfg = SimulationConfig(
        min_latency_ms=5,
        max_latency_ms=8,
        partial_fill_probability=0.0,
        cancel_race_probability=0.0,
        reject_probability=0.0,
    )
    sim = LocalExchangeSimulator(config=cfg, seed=1)

    result = sim.simulate_order(
        OrderIntent(symbol="BTCUSDT", side="buy", quantity=100, price=15000.0)
    )

    assert 5 <= result.latency_ms <= 8
    assert result.status == "filled"
    assert result.filled_quantity == 100


def test_simulator_forced_partial_fill():
    cfg = SimulationConfig(
        min_latency_ms=1,
        max_latency_ms=1,
        partial_fill_probability=1.0,
        cancel_race_probability=0.0,
        reject_probability=0.0,
    )
    sim = LocalExchangeSimulator(config=cfg, seed=2)

    result = sim.simulate_order(
        OrderIntent(symbol="BTCUSDT", side="buy", quantity=100, price=15000.0)
    )

    names = [event.name for event in result.events]
    assert "partial_fill" in names
    assert result.status == "filled"
    assert result.remaining_quantity == 0


def test_simulator_cancel_race_path():
    cfg = SimulationConfig(
        min_latency_ms=1,
        max_latency_ms=1,
        partial_fill_probability=1.0,
        cancel_race_probability=1.0,
        reject_probability=0.0,
    )
    sim = LocalExchangeSimulator(config=cfg, seed=3)

    result = sim.simulate_order(
        OrderIntent(symbol="EURUSD=X", side="sell", quantity=100, price=8000.0)
    )

    names = [event.name for event in result.events]
    assert "cancel_race" in names
    assert result.filled_quantity > 0
    assert result.filled_quantity <= 100
    assert result.status in {"filled", "partially_filled"}
