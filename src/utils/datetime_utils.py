"""Datetime helper utilities.

Provide timezone-aware conversions to avoid deprecated ``utcfromtimestamp``
usages.  Also export Jakarta (WIB, UTC+7) timezone helpers so that active
modules do **not** need to import from the legacy ``idx_api_client``.
"""
from __future__ import annotations

import datetime
from typing import Union


# ---------------------------------------------------------------------------
# Jakarta / WIB timezone (UTC+7) — shared utility
# ---------------------------------------------------------------------------

JAKARTA_TZ = datetime.timezone(datetime.timedelta(hours=7))


def get_jakarta_now() -> datetime.datetime:
    """Return current time in Jakarta (WIB, UTC+7)."""
    return datetime.datetime.now(JAKARTA_TZ)


def to_jakarta_time(dt: datetime.datetime) -> datetime.datetime:
    """Convert any datetime to Jakarta (WIB, UTC+7).

    If ``dt`` is naive it is assumed to be in UTC first.
    """
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=datetime.timezone.utc)
    return dt.astimezone(JAKARTA_TZ)


# ---------------------------------------------------------------------------
# Generic UTC helpers
# ---------------------------------------------------------------------------

def utcnow() -> datetime.datetime:
    """Return the current UTC time as a timezone-aware datetime."""
    return datetime.datetime.now(datetime.timezone.utc)


def fromtimestamp_utc(ts: Union[int, float, str]) -> datetime.datetime:
    """Return a timezone-aware UTC ``datetime`` for the given POSIX timestamp.

    Args:
        ts: POSIX timestamp (int/float) or numeric string.

    Returns:
        datetime.datetime with tzinfo=datetime.timezone.utc
    """
    if isinstance(ts, str):
        ts = float(ts)
    return datetime.datetime.fromtimestamp(float(ts), datetime.timezone.utc)


def to_local(dt: datetime.datetime) -> datetime.datetime:
    """Convert a timezone-aware UTC datetime to local time.

    If ``dt`` is naive, treat it as UTC first.
    """
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=datetime.timezone.utc)
    return dt.astimezone()
