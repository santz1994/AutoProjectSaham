"""Very small backtester for strategy signals.

This is intentionally tiny — meant for quick verification and iterative development.
"""

def simple_backtest(prices, signals, starting_cash=10000.0):
    cash = float(starting_cash)
    pos = 0
    trades = []

    for i, price in enumerate(prices):
        sig = signals[i]
        if sig == 1:
            # buy 1 lot (100 shares) when signalled — IDX uses lot-based trading
            lot_size = 100
            qty = 1 * lot_size
            cost = price * qty
            if cost <= cash:
                cash -= cost
                pos += qty
                trades.append(('buy', i, price, qty))
        elif sig == -1 and pos > 0:
            qty = pos
            cash += price * qty
            trades.append(('sell', i, price, qty))
            pos = 0

    final_bal = cash + pos * (prices[-1] if prices else 0)
    return {'final_balance': final_bal, 'trades': trades}
