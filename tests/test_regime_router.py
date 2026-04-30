import numpy as np

from src.ml.regime_router import apply_regime_overlay, classify_market_regime


def test_classify_market_regime_bull_route():
    prices = np.linspace(100.0, 120.0, 60)
    route = classify_market_regime(prices)

    assert route.regime == "BULL"
    assert route.primary_agent == "bull_agent"
    assert route.risk_multiplier == 1.0


def test_classify_market_regime_bear_route():
    prices = np.linspace(120.0, 95.0, 60)
    route = classify_market_regime(prices)

    assert route.regime == "BEAR"
    assert route.primary_agent == "bear_agent"
    assert route.risk_multiplier < 1.0


def test_apply_regime_overlay_downgrades_buy_on_bear_conflict():
    prices = np.linspace(130.0, 100.0, 60)
    route = classify_market_regime(prices)
    assert route.regime == "BEAR"

    signal, expected_return, note = apply_regime_overlay(
        signal="BUY",
        expected_return=0.04,
        model_confidence=0.65,
        route=route,
    )

    assert signal == "HOLD"
    assert expected_return <= 0.0
    assert "BEAR" in note
