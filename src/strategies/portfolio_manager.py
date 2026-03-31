"""Portfolio utilities: correlation-based signal filtering and risk parity helpers.
"""
from __future__ import annotations

from typing import List

import pandas as pd


def filter_correlated_signals(
    new_buy_signals: List[str],
    current_portfolio_symbols: List[str],
    historical_returns: pd.DataFrame,
    max_correlation: float = 0.65,
) -> List[str]:
    """
    Filter new buy signals based on Pearson correlation against current holdings.

    Returns a list of approved symbols (subset of new_buy_signals).
    """
    approved_signals = []

    if historical_returns.empty:
        return new_buy_signals

    corr_matrix = historical_returns.corr()

    for symbol in new_buy_signals:
        is_safe = True
        for holding in current_portfolio_symbols:
            if symbol in corr_matrix.columns and holding in corr_matrix.columns:
                correlation = corr_matrix.loc[symbol, holding]
                if correlation > float(max_correlation):
                    is_safe = False
                    # Log can be added by caller
                    break
        if is_safe:
            approved_signals.append(symbol)

    return approved_signals
