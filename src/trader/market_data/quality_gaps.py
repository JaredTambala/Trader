"""Pure gap analysis helpers for market-data quality reports.

This module owns deterministic timestamp-gap classification for the
`run_data_quality` entrypoint. Event-store access,
logging, clocks, and filesystem writes stay in `trader.market_data.quality`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from itertools import islice
from typing import Literal, Mapping, Sequence
from zoneinfo import ZoneInfo

from ..timeframes import normalize_timeframe, parse_timeframe


_MARKET_TZ = ZoneInfo("America/New_York")
DEFAULT_MAX_GAP_SAMPLES = 100

CompletenessClassification = Literal[
    "exchange_closure",
    "asset_not_listed",
    "asset_delisted",
    "illiquid_no_trade",
    "provider_zero_activity",
    "provider_coverage_gap",
    "local_ingestion_loss",
    "unclassified_gap",
]


@dataclass(frozen=True)
class BarObservation:
    """Raw bar facts used to distinguish no-trade observations from omissions.

    The quality engine deliberately keeps these facts separate from inferred
    completeness.  A provider-emitted zero-volume bar is evidence that the
    provider answered for a minute; it is not evidence of local ingestion loss.
    """

    ts: datetime
    volume: float | None = None
    trade_count: float | None = None
    source: str | None = None

    @property
    def zero_activity(self) -> bool:
        """Return whether the provider explicitly emitted no activity."""
        return (self.volume is not None and self.volume == 0) or (
            self.trade_count is not None and self.trade_count == 0
        )


@dataclass(frozen=True)
class AssetLifecycle:
    """Listing bounds for one asset, inclusive at each observed boundary."""

    listed_at: datetime | None = None
    delisted_at: datetime | None = None


@dataclass(frozen=True)
class ProviderCoverageWindow:
    """Provider coverage fact for a bounded interval.

    ``available=False`` records a provider-wide hole.  ``affected_symbols``
    may be empty when the provider evidence applies to the whole requested
    universe.
    """

    start: datetime
    end: datetime
    available: bool
    provider: str | None = None
    affected_symbols: tuple[str, ...] = ()


@dataclass(frozen=True)
class CompletenessContext:
    """Asset and provider facts required for actionable gap classification."""

    lifecycle: Mapping[str, AssetLifecycle] = field(default_factory=dict)
    provider_windows: tuple[ProviderCoverageWindow, ...] = ()
    provider_omits_no_trade: frozenset[str] = frozenset()
    provider: str | None = None

    def lifecycle_for(self, symbol: str) -> AssetLifecycle | None:
        """Return lifecycle metadata using canonical case-insensitive lookup."""
        return self.lifecycle.get(symbol) or self.lifecycle.get(symbol.upper())


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
        reason: Stable legacy-neutral reason for the gap (``gap`` or
            ``expected_session_gap``).
        classification: Asset-aware classification used by callers to decide
            whether to repair, exclude, or accept the interval.
        raw_facts: Provider, lifecycle, and policy facts retained with the
            inferred classification.
    """

    symbol: str
    prev_ts: datetime
    next_ts: datetime
    delta: timedelta
    expected: timedelta
    threshold: timedelta
    reason: str
    classification: CompletenessClassification = "unclassified_gap"
    raw_facts: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class DataQualitySummary:
    """Per-symbol aggregate counts produced by data-quality checks.

    Attributes:
        symbol: Canonical symbol.
        total_bars: Number of observed bars.
        missing_gaps: Number of gaps classified as missing data.
        expected_gaps: Number of gaps classified as expected session downtime.
        max_gap: Largest adjacent timestamp delta, if enough bars exist.
        classifications: Counts keyed by asset-aware classification.
        zero_activity_bars: Provider-emitted bars with explicit zero activity.
        action: Highest-priority action for the symbol.
    """

    symbol: str
    total_bars: int
    missing_gaps: int
    expected_gaps: int
    max_gap: timedelta | None
    classifications: Mapping[str, int] = field(default_factory=dict)
    zero_activity_bars: int = 0
    action: str = "review"


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
    max_gap_samples: int = DEFAULT_MAX_GAP_SAMPLES,
    observations: Sequence[BarObservation] | None = None,
    context: CompletenessContext | None = None,
) -> tuple[DataQualitySummary, list[GapRecord]]:
    """Classify oversized timestamp gaps for one symbol.

    Args:
        symbol: Canonical symbol being analyzed.
        timestamps: Ordered timestamps to inspect.
        asset_class: Market-data asset class.
        timeframe: Normalized timeframe string.
        multipliers: Gap-threshold multipliers keyed by timeframe unit.
        sessions: Optional symbol/timeframe session overrides.
        max_gap_samples: Maximum detailed gaps retained per symbol. Zero keeps
            aggregate counts without detail.
        observations: Optional raw bar facts. When supplied, zero-activity
            provider bars are counted without turning them into missing gaps.
        context: Optional listing, provider-coverage, and no-trade evidence.

    Returns:
        Per-symbol complete summary and at most `max_gap_samples` gap records.

    Raises:
        ValueError: If the sample bound is negative or is not an integer.
    """
    if isinstance(max_gap_samples, bool) or not isinstance(max_gap_samples, int) or max_gap_samples < 0:
        raise ValueError("max_gap_samples must be a non-negative integer")
    effective_context = context or CompletenessContext()
    classification_counts: dict[str, int] = {}
    zero_activity_bars = sum(
        1 for observation in (observations or ()) if observation.zero_activity
    )
    if len(timestamps) < 2:
        summary = DataQualitySummary(
            symbol=symbol,
            total_bars=len(timestamps),
            missing_gaps=0,
            expected_gaps=0,
            max_gap=None,
            classifications=(
                {"provider_zero_activity": zero_activity_bars}
                if zero_activity_bars
                else {}
            ),
            zero_activity_bars=zero_activity_bars,
            action="review" if not timestamps else "usable",
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

    for prev_ts, next_ts in zip(timestamps, islice(timestamps, 1, None)):
        delta = next_ts - prev_ts
        if max_gap is None or delta > max_gap:
            max_gap = delta
        if delta <= threshold:
            continue
        session = sessions.get((symbol.upper(), normalize_timeframe(timeframe)))
        reason = gap_reason(prev_ts, next_ts, asset_class, timeframe, session=session)
        classification = classify_gap(
            symbol=symbol,
            prev_ts=prev_ts,
            next_ts=next_ts,
            asset_class=asset_class,
            reason=reason,
            context=effective_context,
        )
        classification_counts[classification] = classification_counts.get(classification, 0) + 1
        if len(gaps) < max_gap_samples:
            gaps.append(
                GapRecord(
                    symbol=symbol,
                    prev_ts=prev_ts,
                    next_ts=next_ts,
                    delta=delta,
                    expected=expected_delta,
                    threshold=threshold,
                    reason=reason,
                    classification=classification,
                    raw_facts=_raw_gap_facts(
                        symbol=symbol,
                        asset_class=asset_class,
                        classification=classification,
                        context=effective_context,
                    ),
                )
            )
        if classification == "exchange_closure":
            expected += 1
        else:
            missing += 1

    if zero_activity_bars:
        classification_counts["provider_zero_activity"] = zero_activity_bars

    summary = DataQualitySummary(
        symbol=symbol,
        total_bars=len(timestamps),
        missing_gaps=missing,
        expected_gaps=expected,
        max_gap=max_gap,
        classifications=classification_counts,
        zero_activity_bars=zero_activity_bars,
        action=_symbol_action(classification_counts, has_bars=bool(timestamps)),
    )
    return summary, gaps


def classify_gap(
    *,
    symbol: str,
    prev_ts: datetime,
    next_ts: datetime,
    asset_class: str,
    reason: str,
    context: CompletenessContext,
) -> CompletenessClassification:
    """Classify an absent interval using explicit asset/provider evidence."""
    lifecycle = context.lifecycle_for(symbol)
    if lifecycle is not None:
        if lifecycle.listed_at is not None and next_ts <= lifecycle.listed_at:
            return "asset_not_listed"
        if lifecycle.delisted_at is not None and prev_ts >= lifecycle.delisted_at:
            return "asset_delisted"
    if reason == "expected_session_gap":
        return "exchange_closure"
    if _matches_provider_window(symbol, prev_ts, next_ts, context, available=False):
        return "provider_coverage_gap"
    if symbol.upper() in {item.upper() for item in context.provider_omits_no_trade}:
        return "illiquid_no_trade"
    if _matches_provider_window(symbol, prev_ts, next_ts, context, available=True):
        return "local_ingestion_loss"
    return "unclassified_gap"


def _matches_provider_window(
    symbol: str,
    prev_ts: datetime,
    next_ts: datetime,
    context: CompletenessContext,
    *,
    available: bool,
) -> bool:
    """Return whether an interval is covered by matching provider evidence."""
    for window in context.provider_windows:
        symbols = {value.upper() for value in window.affected_symbols}
        applies = not symbols or symbol.upper() in symbols
        if applies and window.available is available and window.start <= prev_ts and next_ts <= window.end:
            return True
    return False


def _raw_gap_facts(
    *,
    symbol: str,
    asset_class: str,
    classification: CompletenessClassification,
    context: CompletenessContext,
) -> dict[str, object]:
    """Retain the inputs that explain an inferred classification."""
    lifecycle = context.lifecycle_for(symbol)
    return {
        "symbol": symbol,
        "asset_class": asset_class,
        "provider": context.provider,
        "classification": classification,
        "listed_at": lifecycle.listed_at.isoformat() if lifecycle and lifecycle.listed_at else None,
        "delisted_at": lifecycle.delisted_at.isoformat() if lifecycle and lifecycle.delisted_at else None,
    }


def _symbol_action(classifications: Mapping[str, int], *, has_bars: bool) -> str:
    """Return the actionable disposition for a symbol's quality evidence."""
    if not has_bars:
        return "no_observations"
    if classifications.get("local_ingestion_loss"):
        return "repair_local_ingestion"
    if classifications.get("provider_coverage_gap"):
        return "await_provider_coverage"
    if classifications.get("unclassified_gap"):
        return "investigate_gap"
    if classifications.get("illiquid_no_trade"):
        return "accept_sparse_activity"
    if classifications.get("asset_not_listed") or classifications.get("asset_delisted"):
        return "outside_asset_lifecycle"
    if classifications.get("exchange_closure"):
        return "expected_exchange_closure"
    return "usable"


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
