"""Utility helpers for auth guard and kill-switch challenge verification."""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import os
from datetime import datetime
from typing import Optional


def env_flag(name: str, default: bool = False) -> bool:
    raw = str(os.getenv(name, "")).strip().lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "on"}


def parse_csv_set(value: str) -> set[str]:
    return {
        item.strip().lower()
        for item in str(value or "").split(",")
        if item.strip()
    }


def totp_code_at(
    secret: str,
    timestamp: int,
    *,
    step_seconds: int = 30,
    digits: int = 6,
) -> Optional[str]:
    normalized_secret = "".join(str(secret or "").strip().split()).upper()
    if not normalized_secret:
        return None

    try:
        secret_bytes = base64.b32decode(normalized_secret, casefold=True)
    except (binascii.Error, ValueError, TypeError):
        return None

    step = max(1, int(step_seconds))
    counter = int(timestamp // step)
    msg = counter.to_bytes(8, "big")
    digest = hmac.new(secret_bytes, msg, hashlib.sha1).digest()
    offset = digest[-1] & 0x0F

    binary_code = (
        ((digest[offset] & 0x7F) << 24)
        | (digest[offset + 1] << 16)
        | (digest[offset + 2] << 8)
        | digest[offset + 3]
    )

    modulus = 10 ** max(1, int(digits))
    return str(binary_code % modulus).zfill(max(1, int(digits)))


def verify_totp_code(
    secret: str,
    code: str,
    *,
    step_seconds: int = 30,
    window: int = 1,
) -> bool:
    normalized_code = str(code or "").strip()
    if not normalized_code or not normalized_code.isdigit():
        return False

    now_ts = int(datetime.now().timestamp())
    valid_window = max(0, int(window))
    for drift in range(-valid_window, valid_window + 1):
        current_ts = now_ts + drift * int(step_seconds)
        expected = totp_code_at(
            secret,
            current_ts,
            step_seconds=step_seconds,
            digits=len(normalized_code),
        )
        if expected and hmac.compare_digest(expected, normalized_code):
            return True

    return False
