"""Shared broker normalization helpers."""

from __future__ import annotations

from typing import Any, cast


def coerce_float(value: object | None, *, default: float = 0.0) -> float:
    """Coerce provider/config values to float without raising on bad payloads.

    Broker adapters use this at external boundaries where providers may return
    numbers as strings or omit optional fields. Invalid values fall back to the
    caller-supplied default so response normalization remains total.
    """
    if value is None:
        return default
    try:
        return float(cast(Any, value))
    except (TypeError, ValueError):
        return default
