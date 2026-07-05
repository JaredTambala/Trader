"""Pure market-data readiness checks for decision cycles."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Sequence

from ..market_data import MarketDataEvent


@dataclass(frozen=True)
class MarketDataReadiness:
    """Pure assessment of whether market data is usable for a trading decision."""

    should_skip: bool
    max_age_seconds: int
    latest_ts: datetime | None
    age_seconds: float | None
    is_stale: bool
    reason: str | None


@dataclass(frozen=True)
class MarketDataEventFreshness:
    """Pure freshness assessment for one streaming market-data event."""

    ts: datetime
    age_seconds: float
    max_age_seconds: int
    is_stale: bool


def assess_market_data_readiness(
    market_data_events: Sequence[MarketDataEvent],
    *,
    now: datetime,
    max_age_seconds: int,
) -> MarketDataReadiness:
    """Assess market-data availability and freshness without side effects.

    Args:
        market_data_events: Market-data events available to the cycle.
        now: Timestamp used for staleness comparison.
        max_age_seconds: Maximum allowed age in seconds.

    Returns:
        Immutable readiness result describing whether trading should be skipped.

    Raises:
        ValueError: If `max_age_seconds` is negative.
    """
    if max_age_seconds < 0:
        raise ValueError("max_age_seconds must be non-negative")
    if not market_data_events:
        return MarketDataReadiness(
            should_skip=True,
            max_age_seconds=max_age_seconds,
            latest_ts=None,
            age_seconds=None,
            is_stale=False,
            reason="missing_market_data",
        )
    normalized_now = _normalize_timestamp(now)
    latest_ts = max(_normalize_timestamp(event.ts) for event in market_data_events)
    age_seconds = (normalized_now - latest_ts).total_seconds()
    is_stale = age_seconds > max_age_seconds
    return MarketDataReadiness(
        should_skip=is_stale,
        max_age_seconds=max_age_seconds,
        latest_ts=latest_ts,
        age_seconds=age_seconds,
        is_stale=is_stale,
        reason="stale_market_data" if is_stale else None,
    )


def assess_market_data_event_freshness(
    event: MarketDataEvent,
    *,
    now: datetime,
    max_age_seconds: int,
) -> MarketDataEventFreshness:
    """Assess freshness for one market-data event without side effects.

    Args:
        event: Market-data event being considered by streaming mode.
        now: Timestamp used for staleness comparison.
        max_age_seconds: Maximum allowed age in seconds.

    Returns:
        Immutable freshness result with normalized timestamp and age.

    Raises:
        ValueError: If `max_age_seconds` is negative.
    """
    if max_age_seconds < 0:
        raise ValueError("max_age_seconds must be non-negative")
    ts = _normalize_timestamp(event.ts)
    age_seconds = (_normalize_timestamp(now) - ts).total_seconds()
    is_stale = age_seconds > max_age_seconds
    return MarketDataEventFreshness(
        ts=ts,
        age_seconds=age_seconds,
        max_age_seconds=max_age_seconds,
        is_stale=is_stale,
    )


def _is_event_stale(event: MarketDataEvent, now: datetime, max_age_seconds: int) -> bool:
    """Return whether one market-data event is older than the allowed window."""
    return assess_market_data_event_freshness(
        event,
        now=now,
        max_age_seconds=max_age_seconds,
    ).is_stale


def _normalize_timestamp(timestamp: datetime) -> datetime:
    """Normalize timestamps to timezone-aware UTC.

    Args:
        timestamp: Input timestamp.

    Returns:
        UTC-aware datetime.
    """
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=timezone.utc)
    return timestamp.astimezone(timezone.utc)


__all__ = [
    "MarketDataEventFreshness",
    "MarketDataReadiness",
    "assess_market_data_event_freshness",
    "assess_market_data_readiness",
]
