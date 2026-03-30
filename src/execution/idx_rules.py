"""IDX guardrails and fraksi harga (tick-size) helpers.

Provides functions to compute ARA / ARB limits and round them to valid
tick increments (fraksi harga). This contains a reasonable heuristic for
tick sizes; validate against official IDX rulebook in production.
"""
import math


def fraksi_harga_tick(price: float) -> int:
    """Return a sensible tick size (IDR) for a given price using heuristic tiers.

    NOTE: These tiers are heuristic and should be verified with IDX documentation.
    """
    p = float(price)
    if p < 200:
        return 1
    if p < 500:
        return 2
    if p < 2000:
        return 5
    if p < 5000:
        return 10
    if p < 20000:
        return 25
    if p < 100000:
        return 50
    return 100


def round_down_to_tick(price: float, tick: int) -> int:
    return int(math.floor(price / tick) * tick)


def round_up_to_tick(price: float, tick: int) -> int:
    return int(math.ceil(price / tick) * tick)


def calculate_idx_limits(previous_close: float) -> dict:
    """Calculate ARA and ARB limits for a given previous close price.

    Returns a dict: {'ara': <max_buy_price>, 'arb': <min_sell_price>, 'tick': <tick>}
    Prices are rounded to the nearest tick size.
    """
    # ARB is a flat 15% as of the referenced rules
    arb_percentage = 0.15

    # ARA tiers (heuristic)
    if previous_close < 200:
        ara_percentage = 0.35
    elif 200 <= previous_close <= 5000:
        ara_percentage = 0.25
    else:
        ara_percentage = 0.20

    raw_ara = previous_close * (1 + ara_percentage)
    raw_arb = previous_close * (1 - arb_percentage)

    tick = fraksi_harga_tick(previous_close)

    ara = round_down_to_tick(raw_ara, tick)
    arb = round_up_to_tick(raw_arb, tick)

    return {'ara': int(ara), 'arb': int(arb), 'tick': int(tick)}


if __name__ == '__main__':
    print(calculate_idx_limits(10000))
