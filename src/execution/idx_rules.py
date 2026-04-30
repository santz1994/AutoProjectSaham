"""IDX guardrails and fraksi harga (tick-size) helpers.

Provides functions to compute ARA / ARB limits and round them to valid
tick increments (fraksi harga). This contains a reasonable heuristic for
tick sizes; validate against official IDX rulebook in production.
"""
import math


REGULAR_MIN_PRICE = 50
FCA_MIN_PRICE = 1


def fraksi_harga_tick(price: float) -> int:
    """Return a sensible tick size (IDR) for a given price using heuristic tiers.

    NOTE: These tiers are heuristic and should be verified with IDX documentation.
    """
    p = max(0.0, float(price))
    if p < 200:
        return 1
    if p < 500:
        return 2
    if p < 2000:
        return 5
    if p < 5000:
        return 10
    # Per BEI rules, tick size tops out at 25 IDR for prices >= 5,000
    return 25


def round_down_to_tick(price: float, tick: int) -> int:
    return int(math.floor(price / tick) * tick)


def round_up_to_tick(price: float, tick: int) -> int:
    return int(math.ceil(price / tick) * tick)


def round_down_to_valid_tick(price: float) -> int:
    """Round down using tick derived from the target price level."""
    target = max(0.0, float(price))
    target_tick = fraksi_harga_tick(target)
    return round_down_to_tick(target, target_tick)


def round_up_to_valid_tick(price: float) -> int:
    """Round up using tick derived from the target price level."""
    target = max(0.0, float(price))
    target_tick = fraksi_harga_tick(target)
    return round_up_to_tick(target, target_tick)


def calculate_idx_limits(previous_close: float, is_fca: bool = False) -> dict:
    """Calculate ARA and ARB limits for a given previous close price.

    Supports BEI's Full Call Auction (FCA) board via `is_fca`.

    Returns a dict: {'ara': <max_buy_price>, 'arb': <min_sell_price>, 'tick': <tick>}.
    Prices are rounded to the nearest tick size. For FCA boards the limit
    percentage is 10%% and the minimum ARB floor is Rp1. For regular/primary
    boards the percentage is tiered and the ARB floor is Rp50.
    """
    tick = fraksi_harga_tick(previous_close)

    # FCA / Papan Pemantauan Khusus: fixed +/-10%, ARB may go down to Rp1
    if is_fca:
        limit_percentage = 0.10
        raw_ara = previous_close * (1 + limit_percentage)
        raw_arb = previous_close * (1 - limit_percentage)

        ara = round_down_to_valid_tick(raw_ara)
        arb = max(FCA_MIN_PRICE, round_up_to_valid_tick(raw_arb))

        return {
            "ara": int(ara),
            "arb": int(arb),
            "tick": int(tick),
            "araTick": int(fraksi_harga_tick(ara)),
            "arbTick": int(fraksi_harga_tick(arb)),
        }

    # Regular / Main board: symmetric tiered percentages
    if previous_close < 200:
        limit_percentage = 0.35
    elif 200 <= previous_close <= 5000:
        limit_percentage = 0.25
    else:
        limit_percentage = 0.20

    raw_ara = previous_close * (1 + limit_percentage)
    raw_arb = previous_close * (1 - limit_percentage)

    # IMPORTANT: Tick size follows the resulting price level, not only
    # the previous close tier. This prevents invalid prices when crossing
    # tier boundaries (e.g. 490 -> ARA around 612.5 should use tick 5).
    ara = round_down_to_valid_tick(raw_ara)
    arb = max(REGULAR_MIN_PRICE, round_up_to_valid_tick(raw_arb))

    return {
        "ara": int(ara),
        "arb": int(arb),
        "tick": int(tick),
        "araTick": int(fraksi_harga_tick(ara)),
        "arbTick": int(fraksi_harga_tick(arb)),
    }


if __name__ == "__main__":
    print(calculate_idx_limits(10000))
