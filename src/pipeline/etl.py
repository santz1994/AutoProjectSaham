"""ETL orchestration for autonomous data pipeline.

This file orchestrates connectors and returns collected data structures.
"""

def run_etl(symbols, start_date=None, end_date=None, news_api_key=None):
    data = {}

    # Stocks / IDX
    try:
        from .data_connectors.idx_connector import fetch_idx

        data['stocks'] = fetch_idx(symbols, start_date=start_date, end_date=end_date)
    except Exception as e:
        data['stocks_error'] = repr(e)

    # Forex
    try:
        from .data_connectors.forex_connector import fetch_forex_time_series
        data['forex'] = fetch_forex_time_series()
    except Exception as e:
        data['forex_error'] = repr(e)

    # News
    try:
        from .data_connectors.news_connector import fetch_news
        data['news'] = fetch_news(' '.join(symbols), api_key=news_api_key)
    except Exception as e:
        data['news_error'] = repr(e)

    return data
