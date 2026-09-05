"""Pure gap analysis helpers for market-data quality reports.

This module owns deterministic timestamp-gap classification and report payload
construction for the legacy `run_data_quality` entrypoint. Event-store access,
logging, clocks, and filesystem writes stay in `trader.market_data.quality`.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Mapping, Sequence
from zoneinfo import ZoneInfo

from ..timeframes import normalize_timeframe, parse_timeframe


_MARKET_TZ = ZoneInfo("America/New_York")


@dataclass(frozen=True)
class GapRecord:
    """One timestamp discontinuity detected during bar coverage analysis.

    Attributes:
        symbol: Canonical symbol for the gap.
        prev_ts: Timestamp immediately before the gap.
        next_ts: Timestamp immediately after the gap.
        delta: Observed time delta between adjacent bars.
        expected: Nominal expected delta for the timeframe.
        threshold: Gap threshold used for classification.
        reason: Stable reason code for the gap classification.
    """

    symbol: str
    prev_ts: datetime
    next_ts: datetime
    delta: timedelta
    expected: timedelta
    threshold: timedelta
    reason: str


@dataclass(frozen=True)
class DataQualitySummary:
    """Per-symbol aggregate counts produced by data-quality checks.

    Attributes:
        symbol: Canonical symbol.
        total_bars: Number of observed bars.
        missing_gaps: Number of gaps classified as missing data.
        expected_gaps: Number of gaps classified as expected session downtime.
        max_gap: Largest adjacent timestamp delta, if enough bars exist.
    """

    symbol: str
    total_bars: int
    missing_gaps: int
    expected_gaps: int
    max_gap: timedelta | None


@dataclass(frozen=True)
class SessionWindow:
    """Trading-session window used to classify expected downtime.

    Attributes:
        symbol: Canonical symbol the session applies to.
        timeframe: Normalized timeframe the session applies to.
        start_time: Local session open time.
        end_time: Local session close time.
        timezone: Local session timezone.
    """

    symbol: str
    timeframe: str
    start_time: time
    end_time: time
    timezone: ZoneInfo


def analyze_gaps(
    *,
    symbol: str,
    timestamps: Sequence[datetime],
    asset_class: str,
    timeframe: str,
    multipliers: Mapping[str, float],
    sessions: Mapping[tuple[str, str], SessionWindow],
) -> tuple[DataQualitySummary, list[GapRecord]]:
    """Classify oversized timestamp gaps for one symbol.

    Args:
        symbol: Canonical symbol being analyzed.
        timestamps: Ordered timestamps to inspect.
        asset_class: Market-data asset class.
        timeframe: Normalized timeframe string.
        multipliers: Gap-threshold multipliers keyed by timeframe unit.
        sessions: Optional symbol/timeframe session overrides.

    Returns:
        Per-symbol summary and detailed gap records.
    """
    if len(timestamps) < 2:
        summary = DataQualitySummary(
            symbol=symbol,
            total_bars=len(timestamps),
            missing_gaps=0,
            expected_gaps=0,
            max_gap=None,
        )
        return summary, []

    expected_delta = expected_delta_for_timeframe(timeframe)
    unit = timeframe_unit(timeframe)
    multiplier = multipliers.get(unit, 2.0)
    threshold = expected_delta * multiplier
    gaps: list[GapRecord] = []
    missing = 0
    expected = 0
    max_gap = None

    for prev_ts, next_ts in zip(timestamps, timestamps[1:]):
        delta = next_ts - prev_ts
        if max_gap is None or delta > max_gap:
            max_gap = delta
        if delta <= threshold:
            continue
        session = sessions.get((symbol.upper(), normalize_timeframe(timeframe)))
        reason = gap_reason(prev_ts, next_ts, asset_class, timeframe, session=session)
        record = GapRecord(
            symbol=symbol,
            prev_ts=prev_ts,
            next_ts=next_ts,
            delta=delta,
            expected=expected_delta,
            threshold=threshold,
            reason=reason,
        )
        gaps.append(record)
        if reason == "expected_session_gap":
            expected += 1
        else:
            missing += 1

    summary = DataQualitySummary(
        symbol=symbol,
        total_bars=len(timestamps),
        missing_gaps=missing,
        expected_gaps=expected,
        max_gap=max_gap,
    )
    return summary, gaps


def gap_reason(
    prev_ts: datetime,
    next_ts: datetime,
    asset_class: str,
    timeframe: str,
    *,
    session: SessionWindow | None,
) -> str:
    """Return the data-quality reason code for a timestamp gap.

    Args:
        prev_ts: Timestamp before the gap.
        next_ts: Timestamp after the gap.
        asset_class: Market-data asset class.
        timeframe: Normalized timeframe string.
        session: Optional session override.

    Returns:
        `"expected_session_gap"` for expected downtime; otherwise `"gap"`.
    """
    if asset_class not in {"stocks", "stock"}:
        if session and is_expected_window_gap(prev_ts, next_ts, session):
            return "expected_session_gap"
        return "gap"
    unit = timeframe_unit(timeframe)
    if unit in {"minute", "hour"}:
        if session and is_expected_window_gap(prev_ts, next_ts, session):
            return "expected_session_gap"
        if unit == "minute" and prev_ts.date() != next_ts.date():
            return "expected_session_gap"
        if is_expected_session_gap(prev_ts, next_ts):
            return "expected_session_gap"
    elif unit in {"day", "week", "month"}:
        if is_expected_daily_gap(prev_ts, next_ts, timeframe):
            return "expected_session_gap"
    return "gap"


def is_expected_session_gap(prev_ts: datetime, next_ts: datetime) -> bool:
    """Return whether a stock-market intraday gap is expected downtime.

    Args:
        prev_ts: Timestamp before the gap.
        next_ts: Timestamp after the gap.

    Returns:
        True when the gap spans no more than one trading day.
    """
    prev_local = prev_ts.astimezone(_MARKET_TZ)
    next_local = next_ts.astimezone(_MARKET_TZ)
    if prev_local.date() == next_local.date():
        return False
    trading_days = count_trading_days(prev_local.date(), next_local.date())
    return trading_days <= 1


def is_expected_window_gap(prev_ts: datetime, next_ts: datetime, session: SessionWindow) -> bool:
    """Return whether a gap is expected under a configured session window.

    Args:
        prev_ts: Timestamp before the gap.
        next_ts: Timestamp after the gap.
        session: Trading-session override.

    Returns:
        True when the gap falls between session close and next open.
    """
    prev_local = prev_ts.astimezone(session.timezone)
    next_local = next_ts.astimezone(session.timezone)
    if prev_local.date() == next_local.date():
        return False
    if prev_local.time() < session.end_time:
        return False
    if next_local.time() > session.start_time:
        return False
    return True


def is_expected_daily_gap(prev_ts: datetime, next_ts: datetime, timeframe: str) -> bool:
    """Return whether a day/week/month gap is normal market-calendar downtime.

    Args:
        prev_ts: Timestamp before the gap.
        next_ts: Timestamp after the gap.
        timeframe: Normalized timeframe string.

    Returns:
        True when the trading-day span is within the timeframe tolerance.
    """
    prev_local = prev_ts.astimezone(_MARKET_TZ)
    next_local = next_ts.astimezone(_MARKET_TZ)
    trading_days = count_trading_days(prev_local.date(), next_local.date())
    expected_days = expected_trading_days(timeframe)
    return trading_days <= expected_days


def expected_trading_days(timeframe: str) -> int:
    """Return the approximate trading-day span represented by a timeframe.

    Args:
        timeframe: Timeframe to normalize and inspect.

    Returns:
        Approximate number of trading days represented by one bar.
    """
    tf = normalize_timeframe(timeframe)
    amount, unit = parse_timeframe_parts(tf)
    if unit == "week":
        return amount * 5
    if unit == "month":
        return amount * 21
    return amount


def count_trading_days(start_date: date, end_date: date) -> int:
    """Count weekdays between two dates, excluding the start date.

    Args:
        start_date: Start date, excluded from the count.
        end_date: End date, included in the count.

    Returns:
        Number of weekdays in the interval.
    """
    if end_date <= start_date:
        return 0
    day = start_date + timedelta(days=1)
    count = 0
    while day <= end_date:
        if day.weekday() < 5:
            count += 1
        day += timedelta(days=1)
    return count


def expected_delta_for_timeframe(timeframe: str) -> timedelta:
    """Return the nominal wall-clock delta represented by one bar.

    Args:
        timeframe: Timeframe to parse.

    Returns:
        Nominal timedelta for one bar.
    """
    tf = parse_timeframe(timeframe)
    if tf.unit.name == "Minute":
        return timedelta(minutes=tf.amount)
    if tf.unit.name == "Hour":
        return timedelta(hours=tf.amount)
    if tf.unit.name == "Day":
        return timedelta(days=tf.amount)
    if tf.unit.name == "Week":
        return timedelta(weeks=tf.amount)
    return timedelta(days=30 * tf.amount)


def timeframe_unit(timeframe: str) -> str:
    """Return the coarse unit name for a normalized timeframe string.

    Args:
        timeframe: Timeframe to normalize and inspect.

    Returns:
        One of `minute`, `hour`, `day`, `week`, or `month`.
    """
    tf = normalize_timeframe(timeframe)
    if tf.endswith("Min"):
        return "minute"
    if tf.endswith("Hour"):
        return "hour"
    if tf.endswith("Day"):
        return "day"
    if tf.endswith("Week"):
        return "week"
    if tf.endswith("Month"):
        return "month"
    raise ValueError(f"Unsupported timeframe: {timeframe}")

def parse_timeframe_parts(timeframe: str) -> tuple[int, str]:
    """Return numeric amount and lowercase unit from a normalized timeframe.

    Args:
        timeframe: Timeframe to normalize and inspect.

    Returns:
        Numeric amount and lowercase timeframe unit.
    """
    tf = normalize_timeframe(timeframe)
    for unit in ("Min", "Hour", "Day", "Week", "Month"):
        if tf.endswith(unit):
            amount = int(tf[: -len(unit)])
            return amount, unit.lower()
    raise ValueError(f"Unsupported timeframe: {timeframe}")
