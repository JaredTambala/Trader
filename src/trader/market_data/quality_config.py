"""Config parsing helpers for configured market-data quality checks."""

from __future__ import annotations

from datetime import datetime, time
from typing import Mapping
from zoneinfo import ZoneInfo

from ..timeframes import normalize_timeframe
from .quality_gaps import SessionWindow


def parse_symbols(value: object) -> tuple[str, ...]:
    """Parse configured symbols from a comma string or sequence.

    Args:
        value: Raw config value.

    Returns:
        Uppercase symbol tuple.

    Raises:
        ValueError: If the value is not a supported shape.
    """
    if value is None:
        return tuple()
    if isinstance(value, str):
        symbols = [symbol.strip().upper() for symbol in value.split(",") if symbol.strip()]
        return tuple(symbols)
    if isinstance(value, (list, tuple)):
        symbols = [str(symbol).strip().upper() for symbol in value if str(symbol).strip()]
        return tuple(symbols)
    raise ValueError("data_quality.symbols must be a string or list")


def parse_datetime(value: object | None) -> datetime | None:
    """Parse optional ISO datetime config values for report bounds.

    Args:
        value: Raw datetime config value.

    Returns:
        Parsed datetime, or `None` for blank input.
    """
    if value in {None, ""}:
        return None
    text = str(value)
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    return datetime.fromisoformat(text)


def parse_gap_multipliers(value: object | None) -> dict[str, float]:
    """Parse per-timeframe gap thresholds, merging with defaults.

    Args:
        value: Raw config mapping or `None`.

    Returns:
        Multiplier mapping keyed by timeframe unit.

    Raises:
        ValueError: If the mapping or a value is invalid.
    """
    defaults = {
        "minute": 2.0,
        "hour": 2.0,
        "day": 1.0,
        "week": 1.0,
        "month": 1.0,
    }
    if value is None:
        return defaults
    if not isinstance(value, Mapping):
        raise ValueError("data_quality.gap_multipliers must be a mapping")
    overrides: dict[str, float] = {}
    for key, raw in value.items():
        unit = str(key).lower()
        try:
            overrides[unit] = float(raw)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Invalid gap multiplier for {key}: {raw}") from exc
    defaults.update(overrides)
    return defaults


def parse_sessions(value: object | None) -> dict[tuple[str, str], SessionWindow]:
    """Parse optional symbol/timeframe-specific trading session windows.

    Args:
        value: Raw session config list.

    Returns:
        Session windows keyed by `(symbol, timeframe)`.

    Raises:
        ValueError: If a session entry is malformed.
    """
    if value is None:
        return {}
    if not isinstance(value, (list, tuple)):
        raise ValueError("data_quality.sessions must be a list")
    sessions: dict[tuple[str, str], SessionWindow] = {}
    for entry in value:
        if not isinstance(entry, Mapping):
            raise ValueError("data_quality.sessions entries must be mappings")
        symbol = str(entry.get("symbol", "")).strip().upper()
        if not symbol:
            raise ValueError("data_quality.sessions requires symbol")
        timeframe = normalize_timeframe(str(entry.get("timeframe", "")))
        start_raw = entry.get("start_time")
        end_raw = entry.get("end_time")
        if not start_raw or not end_raw:
            raise ValueError("data_quality.sessions requires start_time and end_time")
        tz_name = str(entry.get("timezone") or "America/New_York")
        timezone = ZoneInfo(tz_name)
        start_time = parse_clock_time(str(start_raw))
        end_time = parse_clock_time(str(end_raw))
        sessions[(symbol, timeframe)] = SessionWindow(
            symbol=symbol,
            timeframe=timeframe,
            start_time=start_time,
            end_time=end_time,
            timezone=timezone,
        )
    return sessions


def parse_clock_time(value: str) -> time:
    """Parse `HH:MM` session-clock values into `datetime.time`.

    Args:
        value: Clock value to parse.

    Returns:
        Parsed time.

    Raises:
        ValueError: If the value is not `HH:MM`.
    """
    parts = value.split(":")
    if len(parts) != 2:
        raise ValueError(f"Invalid time value: {value}")
    hour = int(parts[0])
    minute = int(parts[1])
    return time(hour=hour, minute=minute)


def as_int(value: object | None, default: int) -> int:
    """Coerce a config value into an integer.

    Args:
        value: Raw config value.
        default: Default returned for missing or blank input.

    Returns:
        Parsed integer.

    Raises:
        ValueError: If the value cannot be parsed as an integer.
    """
    if value is None or value == "":
        return default
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid integer value: {value}") from exc


def get_section(data: Mapping[str, object], key: str) -> Mapping[str, object]:
    """Return a nested config section, treating missing/null as empty.

    Args:
        data: Config mapping.
        key: Section name.

    Returns:
        Section mapping, or an empty mapping when absent.

    Raises:
        ValueError: If the section exists but is not a mapping.
    """
    value = data.get(key, {})
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise ValueError(f"Config section '{key}' must be a mapping")
    return value
