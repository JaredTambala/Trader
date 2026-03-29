"""Timeframe parsing and normalization utilities."""

from __future__ import annotations

import re

from alpaca.data.timeframe import TimeFrame, TimeFrameUnit


_TIMEFRAME_RE = re.compile(r"^(\d+)?\s*([A-Za-z]+)$")


def parse_timeframe(value: str) -> TimeFrame:
    """Parse a timeframe string into an Alpaca TimeFrame.

    Args:
        value: Timeframe string (e.g. 5Min, 1h, 1Day, 3Month).

    Returns:
        TimeFrame instance.

    Raises:
        ValueError: If the input is invalid or unsupported.
    """
    raw = value.strip()
    match = _TIMEFRAME_RE.match(raw)
    if not match:
        raise ValueError(f"Invalid timeframe value: {value}")
    amount_raw, unit_token = match.groups()
    amount = int(amount_raw or 1)
    unit_raw = unit_token.lower()
    if unit_token == "M" or unit_raw in {"month", "months", "mo", "mth"}:
        if amount not in {1, 2, 3, 4, 6, 12}:
            raise ValueError("Month timeframe must be 1,2,3,4,6,12")
        unit = TimeFrameUnit.Month
    elif unit_raw in {"min", "mins", "minute", "minutes", "m", "t"}:
        if amount < 1 or amount > 59:
            raise ValueError("Minute timeframe must be 1-59")
        unit = TimeFrameUnit.Minute
    elif unit_raw in {"hour", "hours", "hr", "h"}:
        if amount < 1 or amount > 23:
            raise ValueError("Hour timeframe must be 1-23")
        unit = TimeFrameUnit.Hour
    elif unit_raw in {"day", "days", "d"}:
        if amount != 1:
            raise ValueError("Day timeframe must be 1Day or 1D")
        unit = TimeFrameUnit.Day
    elif unit_raw in {"week", "weeks", "w"}:
        if amount != 1:
            raise ValueError("Week timeframe must be 1Week or 1W")
        unit = TimeFrameUnit.Week
    else:
        raise ValueError(f"Invalid timeframe unit: {unit_raw}")
    return TimeFrame(amount=amount, unit=unit)


def normalize_timeframe(value: str) -> str:
    """Normalize timeframe strings to the canonical Alpaca representation."""
    return str(parse_timeframe(value))
