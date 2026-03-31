"""Simple secrets loader using python-dotenv and os.environ.

Usage:
    from src.utils.secrets import get_secret, SecretsManager
    api = get_secret('ALPHAVANTAGE_API_KEY')

This module intentionally falls back to `os.environ` if a `.env` is not present
or python-dotenv is not installed.
"""
from __future__ import annotations

import os
from typing import Optional

try:
    from dotenv import load_dotenv
except Exception:

    def load_dotenv(path: Optional[str] = None):
        # noop fallback when python-dotenv missing
        return False


_env_loaded = False


def _default_env_path() -> str:
    here = os.path.dirname(__file__)
    project_root = os.path.abspath(os.path.join(here, "..", ".."))
    return os.path.join(project_root, ".env")


def ensure_env(path: Optional[str] = None) -> None:
    global _env_loaded
    if _env_loaded:
        return
    env_path = path or _default_env_path()
    if os.path.exists(env_path):
        try:
            load_dotenv(env_path)
        except Exception:
            # best-effort
            try:
                load_dotenv()
            except Exception:
                pass
    else:
        try:
            load_dotenv()
        except Exception:
            pass
    _env_loaded = True


def get_secret(key: str, default: Optional[str] = None) -> Optional[str]:
    """Return secret from environment or `.env`.

    Does not raise if missing; returns `default` in that case.
    """
    ensure_env()
    return os.environ.get(key, default)


class SecretsManager:
    """Small helper for retrieving secrets with required check."""

    def __init__(self, env_path: Optional[str] = None):
        ensure_env(env_path)

    def get(self, key: str, default: Optional[str] = None) -> Optional[str]:
        return os.environ.get(key, default)

    def require(self, key: str) -> str:
        v = self.get(key)
        if v is None:
            raise KeyError(f"required secret {key} not set")
        return v
