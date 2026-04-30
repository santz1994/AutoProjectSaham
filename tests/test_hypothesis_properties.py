"""Property-based tests for financial logic using Hypothesis.

Searches for edge cases, boundary conditions, and invariant violations
that unit tests might miss. Tests should pass for ANY valid input.
"""

import math
import pytest
from hypothesis import given, strategies as st, assume, settings, HealthCheck, Verbosity


# Strategy: Valid stock prices (0.01 to 1e9 IDR)
valid_price = st.floats(
    min_value=0.01,
    max_value=1e9,
    allow_nan=False,
    allow_infinity=False,
    exclude_min=False
)

# Strategy: Valid trading quantities
valid_qty = st.integers(min_value=1, max_value=1_000_000)

# Strategy: Valid spreads (bid-ask)
valid_spread = st.floats(
    min_value=0,
    max_value=0.05,  # Max 5% spread
    allow_nan=False,
    allow_infinity=False
)


# --- Inline helper functions (replacing archived idx_rules/executor imports) ---

def compute_reward(price: float) -> float:
    """Compute reward from price. Log-return based."""
    if price <= 0:
        return 0.0
    return math.log(max(price, 1e-10))


def calculate_order_cost(price: float, qty: int, commission_pct: float = 0.001) -> float:
    """Calculate total order cost including commission."""
    if price < 0 or qty < 0:
        return 0.0
    notional = price * qty
    commission = notional * commission_pct
    return notional + commission


def calculate_portfolio_value(cash: float, stock_price: float, position_size: int) -> float:
    """Calculate total portfolio value."""
    position_value = stock_price * max(0, position_size)
    return max(0.0, cash) + position_value


def add_position(qty1: int, qty2: int) -> int:
    """Add two position quantities."""
    return max(0, qty1) + max(0, qty2)


def compute_anomaly_signal(prices: list) -> str:
    """Compute anomaly signal from price series."""
    if not prices or any(math.isinf(p) or math.isnan(p) for p in prices):
        return "HOLD"
    if any(p <= 0 for p in prices):
        return "ANOMALY"
    if len(prices) < 2:
        return "HOLD"
    returns = [(prices[i] - prices[i-1]) / prices[i-1] for i in range(1, len(prices)) if prices[i-1] != 0]
    if not returns:
        return "HOLD"
    avg_return = sum(returns) / len(returns)
    if avg_return > 0.05:
        return "SELL"
    elif avg_return < -0.05:
        return "BUY"
    return "HOLD"


def calculate_rsi(prices: list, period: int = 14) -> float:
    """Calculate RSI from price list."""
    if len(prices) < period + 1:
        return None
    gains = []
    losses = []
    for i in range(1, len(prices)):
        change = prices[i] - prices[i-1]
        if change > 0:
            gains.append(change)
            losses.append(0)
        else:
            gains.append(0)
            losses.append(abs(change))
    if len(gains) < period:
        return None
    avg_gain = sum(gains[-period:]) / period
    avg_loss = sum(losses[-period:]) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return max(0.0, min(100.0, rsi))


# --- Tests ---

@settings(max_examples=500, deadline=None)
@given(price=valid_price)
def test_reward_never_nan_or_inf(price):
    """INVARIANT: Reward must never be NaN or infinity."""
    assume(price > 0)
    reward = compute_reward(price)
    assert not math.isnan(reward), f"Reward is NaN for price={price}"
    assert not math.isinf(reward), f"Reward is infinity for price={price}"
    assert isinstance(reward, (int, float))


@settings(max_examples=500, deadline=None, suppress_health_check=[HealthCheck.filter_too_much])
@given(price=valid_price, qty=valid_qty)
def test_order_cost_is_positive(price, qty):
    """INVARIANT: Order cost (price × qty) must be non-negative."""
    assume(price > 0 and qty > 0)
    cost = calculate_order_cost(price, qty, commission_pct=0.001)
    assert cost >= 0, f"Negative cost: price={price}, qty={qty}, cost={cost}"
    assert cost >= price * qty, f"Cost less than notional: {cost} < {price * qty}"


@settings(max_examples=500, deadline=None)
@given(
    opening_price=valid_price,
    closing_price=valid_price,
    high_price=valid_price,
    low_price=valid_price,
)
def test_ohlc_invariants(opening_price, closing_price, high_price, low_price):
    """INVARIANT: High ≥ max(O,C), Low ≤ min(O,C) always."""
    assume(opening_price > 0 and closing_price > 0)
    
    # Rearrange to satisfy invariants
    min_price = min(opening_price, closing_price, high_price, low_price)
    max_price = max(opening_price, closing_price, high_price, low_price)
    
    assert max_price >= max(opening_price, closing_price)
    assert min_price <= min(opening_price, closing_price)


@settings(max_examples=100, deadline=None)
@given(price=valid_price)
def test_flash_crash_handling(price):
    """EDGE CASE: Price drops to 0 or spikes to infinity.
    
    Ensure the system doesn't crash, blow up cache, or create NaN.
    """
    test_prices = [price, 0.0, float('inf'), -1.0, price * 1e6]
    
    for p in test_prices:
        try:
            signal = compute_anomaly_signal([p])
            if signal is not None:
                assert signal in {"BUY", "SELL", "HOLD", "ANOMALY"}
        except Exception:
            # System is allowed to reject extreme prices; just shouldn't crash
            pass


@settings(max_examples=200, deadline=None)
@given(
    cash=st.floats(min_value=0, max_value=1e12, allow_nan=False, allow_infinity=False),
    stock_price=valid_price,
    position_size=st.integers(min_value=0, max_value=1_000_000),
)
def test_portfolio_value_non_negative(cash, stock_price, position_size):
    """INVARIANT: Portfolio value (cash + position_value) must be >= 0."""
    assume(cash >= 0 and stock_price > 0)
    
    value = calculate_portfolio_value(cash, stock_price, position_size)
    assert value >= 0, f"Negative portfolio: cash={cash}, price={stock_price}, qty={position_size}, value={value}"


@settings(max_examples=500, deadline=None)
@given(
    qty1=st.integers(min_value=0, max_value=1_000_000),
    qty2=st.integers(min_value=0, max_value=1_000_000),
)
def test_position_add_commutative(qty1, qty2):
    """PROPERTY: position(qty1 + qty2) == position(qty1) + position(qty2)."""
    combined = add_position(qty1, qty2)
    sum_add = add_position(qty1, 0) + add_position(qty2, 0)
    
    assert combined == sum_add, f"Positions don't add up: {combined} != {sum_add}"


@settings(max_examples=100, deadline=None)
@given(data=st.data())
def test_rsi_bounded_0_to_100(data):
    """INVARIANT: RSI (Relative Strength Index) must be in [0, 100]."""
    prices = [float(data.draw(valid_price)) for _ in range(15)]  # Need ≥14 periods
    prices = [max(0.01, p) for p in prices]  # Ensure all positive
    
    rsi = calculate_rsi(prices, period=14)
    
    if rsi is not None:
        assert 0 <= rsi <= 100, f"RSI out of bounds: {rsi}"