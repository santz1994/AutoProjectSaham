"""Centralized configuration helpers for environment-driven settings.

Keep configuration reads in one place so other modules can import
convenient helpers rather than calling `os.getenv` throughout the code.
"""
from __future__ import annotations

import os
from typing import List


def get_market_symbols() -> List[str]:
    return [s.strip() for s in os.getenv("MARKET_SYMBOLS", "AAPL,SPY").split(",") if s.strip()]


def get_db_path() -> str:
    return os.getenv("TICKS_DB_PATH", "data/ticks.db")


def get_models_dir() -> str:
    return os.getenv("MODELS_DIR", "models")


def get_ml_interval_seconds() -> int:
    try:
        return int(os.getenv("ML_TRAIN_INTERVAL", str(24 * 3600)))
    except Exception:
        return 24 * 3600


def get_alpaca_credentials() -> dict:
    return {
        "key": os.getenv("ALPACA_API_KEY"),
        "secret": os.getenv("ALPACA_SECRET_KEY"),
        "base_url": os.getenv("ALPACA_BASE_URL", "https://api.alpaca.markets"),
    }
