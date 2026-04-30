from src.backtest.vector_backtester import backtest_signals


def test_vector_backtester_max_exposure_blocks_additional_buys():
    prices = [100.0, 100.0, 100.0, 100.0]
    signals = [1, 1, 1, 0]

    result = backtest_signals(
        prices=prices,
        signals=signals,
        initial_cash=10000.0,
        commission_pct=0.0,
        slippage_pct=0.0,
        position_size=50,
        constraints={
            "max_exposure_pct": 0.2,
        },
    )

    buy_trades = [t for t in result["trades"] if t["side"] == "buy"]
    total_bought = sum(int(t["qty"]) for t in buy_trades)

    assert total_bought <= 20
    assert any(e["reason"] == "position_or_exposure_limit" for e in result["constraint_events"])


def test_vector_backtester_drawdown_risk_stop_flattens_position():
    prices = [100.0, 95.0, 90.0, 85.0]
    signals = [1, 0, 0, 0]

    result = backtest_signals(
        prices=prices,
        signals=signals,
        initial_cash=10000.0,
        commission_pct=0.0,
        slippage_pct=0.0,
        position_size=50,
        constraints={
            "max_drawdown_pct": 0.02,
            "flatten_on_risk_stop": True,
        },
    )

    assert result["risk_stop_triggered"] is True
    assert any(e["type"] == "risk_stop" for e in result["constraint_events"])
    assert any(t["side"] == "sell_risk" for t in result["trades"])
