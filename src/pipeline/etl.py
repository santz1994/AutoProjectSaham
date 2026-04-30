"""ETL orchestration for autonomous data pipeline.

This file orchestrates connectors and returns collected data structures.
"""

import os


def run_etl(
    symbols,
    start_date=None,
    end_date=None,
    news_api_key=None,
    corporate_actions_path=None,
):
    data = {}

    # Stocks / IDX
    try:
        from .data_connectors.idx_connector import fetch_idx
        from .corporate_actions import (
            apply_corporate_actions_by_symbol,
            load_corporate_actions,
        )

        stocks = fetch_idx(symbols, start_date=start_date, end_date=end_date)
        data["stocks"] = stocks

        configured_actions = (
            str(corporate_actions_path).strip()
            if corporate_actions_path is not None
            else os.getenv("AUTOSAHAM_CORPORATE_ACTIONS_FILE", "").strip()
        )
        if configured_actions:
            actions_by_symbol = load_corporate_actions(path=configured_actions)
            if actions_by_symbol:
                data["stocks"] = apply_corporate_actions_by_symbol(
                    stocks,
                    actions_by_symbol,
                )
                adjusted_symbols = sorted(
                    {
                        str(symbol).split(".")[0].upper()
                        for symbol in data["stocks"].keys()
                        if str(symbol).split(".")[0].upper() in actions_by_symbol
                    }
                )
                data["stocks_corporate_actions"] = {
                    "applied": True,
                    "source": configured_actions,
                    "configuredSymbols": sorted(actions_by_symbol.keys()),
                    "appliedSymbols": adjusted_symbols,
                }
            else:
                data["stocks_corporate_actions"] = {
                    "applied": False,
                    "source": configured_actions,
                    "configuredSymbols": [],
                    "appliedSymbols": [],
                }
    except (RuntimeError, ValueError, OSError) as e:
        if "stocks" in data:
            data["stocks_corporate_actions_error"] = repr(e)
        else:
            data["stocks_error"] = repr(e)

    # Forex
    try:
        from .data_connectors.forex_connector import fetch_forex_time_series

        data["forex"] = fetch_forex_time_series()
    except (RuntimeError, ValueError, OSError) as e:
        data["forex_error"] = repr(e)

    # News
    try:
        from .data_connectors.news_connector import fetch_news

        data["news"] = fetch_news(" ".join(symbols), api_key=news_api_key)
    except (RuntimeError, ValueError, OSError) as e:
        data["news_error"] = repr(e)

    # Macro positioning (COT)
    try:
        from .data_connectors.cot_connector import fetch_cot_data

        # Default to major FX proxy used in global risk sentiment flows.
        data["cot"] = fetch_cot_data(market="EURUSD")
    except (RuntimeError, ValueError, OSError) as e:
        data["cot_error"] = repr(e)

    return data
