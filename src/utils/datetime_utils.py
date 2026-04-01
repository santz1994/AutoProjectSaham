"""Datetime helper utilities.

Provide timezone-aware conversions to avoid deprecated `utcfromtimestamp` usages.
"""
from __future__ import annotations

import datetime
from typing import Union


def fromtimestamp_utc(ts: Union[int, float, str]) -> datetime.datetime:
    """Return a timezone-aware UTC `datetime` for the given timestamp.

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

    If `dt` is naive, treat it as UTC first.
    """
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=datetime.timezone.utc)
    return dt.astimezone()
