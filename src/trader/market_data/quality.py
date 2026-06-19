"""Typed market-data quality summaries over core market-data queries."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timedelta
import hashlib
import json
import logging
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence
from zoneinfo import ZoneInfo

from ..config import build_config
from ..event_store import EventStore, build_event_store
from ..timeframes import normalize_timeframe, parse_timeframe
from .queries import BarQuery, fetch_bar_timestamps, normalize_bar_query


logger = logging.getLogger(__name__)

_MARKET_TZ = ZoneInfo("America/New_York")
_MARKET_OPEN = time(9, 30)
_MARKET_CLOSE = time(16, 0)


@dataclass(frozen=True)
class SymbolQualitySummary:
    """Quality summary for one requested symbol.

    Attributes:
        symbol: Canonical symbol.
        bar_count: Number of matching bars.
        expected_bar_count: Expected fixed-interval bar count when known.
        first_ts: First observed timestamp, if present.
        last_ts: Last observed timestamp, if present.
        missing_gap_count: Number of detected missing timestamp gaps.
        missing_bar_count: Number of missing fixed-interval bars.
        expected_gap_count: Number of classified expected gaps.
        session_gap_count: Number of classified session gaps.
        max_gap_seconds: Largest detected missing gap in seconds.
        complete: Whether observed bars cover the requested fixed-interval window.
    """

    symbol: str
    bar_count: int
    expected_bar_count: int | None
    first_ts: datetime | None
    last_ts: datetime | None
    missing_gap_count: int
    missing_bar_count: int
    expected_gap_count: int
    session_gap_count: int
    max_gap_seconds: int
    complete: bool

    def to_dict(self) -> dict[str, Any]:
        """Return the summary as a JSON-compatible mapping.

        Returns:
            Dictionary form of the symbol quality summary.
        """
        return {
            "symbol": self.symbol,
            "bar_count": self.bar_count,
            "expected_bar_count": self.expected_bar_count,
            "first_ts": self.first_ts,
            "last_ts": self.last_ts,
            "missing_gap_count": self.missing_gap_count,
            "missing_bar_count": self.missing_bar_count,
            "expected_gap_count": self.expected_gap_count,
            "session_gap_count": self.session_gap_count,
            "max_gap_seconds": self.max_gap_seconds,
            "complete": self.complete,
        }


def summarize_bar_quality(event_store: EventStore, query: BarQuery) -> tuple[dict[str, Any], tuple[str, ...]]:
    """Summarize fixed-interval market-data quality for a bounded query.

    Args:
        event_store: Event store exposing a queryable market-data connection.
        query: Bounded market-data bar query.

    Returns:
        Tuple of quality report payload and non-fatal warnings.

    Raises:
        EventStoreConnectionUnavailable: If no queryable connection is available.
        MarketDataQueryValidationError: If the query is invalid.
    """
    normalized = normalize_bar_query(query)
    bars = fetch_bar_timestamps(event_store, normalized)
    timestamps_by_symbol: dict[str, set[datetime]] = {symbol: set() for symbol in normalized.symbols}
    for bar in bars:
        timestamps_by_symbol.setdefault(bar.symbol, set()).add(bar.ts)

    interval_seconds = _fixed_interval_seconds(normalized.timeframe)
    expected_bar_count = _expected_bar_count(normalized, interval_seconds)
    symbol_summaries: list[SymbolQualitySummary] = []
    warnings: list[str] = []
    for symbol in normalized.symbols:
        summary = _summarize_symbol(
            symbol=symbol,
            timestamps=sorted(timestamps_by_symbol.get(symbol, set())),
            query=normalized,
            interval_seconds=interval_seconds,
            expected_bar_count=expected_bar_count,
        )
        symbol_summaries.append(summary)
        warnings.extend(_symbol_warnings(summary))

    total_bars = sum(summary.bar_count for summary in symbol_summaries)
    missing_gap_count = sum(summary.missing_gap_count for summary in symbol_summaries)
    missing_bar_count = sum(summary.missing_bar_count for summary in symbol_summaries)
    complete = all(summary.complete for summary in symbol_summaries)
    report = {
        "report_id": _report_id(normalized),
        "asset_class": normalized.asset_class,
        "symbols": list(normalized.symbols),
        "timeframe": normalized.timeframe,
        "requested_window": {
            "start": normalized.start,
            "end": normalized.end,
        },
        "source_filter": normalized.source,
        "total_bars": total_bars,
        "missing_gap_count": missing_gap_count,
        "missing_bar_count": missing_bar_count,
        "expected_gap_count": sum(summary.expected_gap_count for summary in symbol_summaries),
        "session_gap_count": sum(summary.session_gap_count for summary in symbol_summaries),
        "max_gap_seconds": max((summary.max_gap_seconds for summary in symbol_summaries), default=0),
        "complete": complete,
        "warnings": warnings,
        "symbols_detail": [summary.to_dict() for summary in symbol_summaries],
    }
    return report, tuple(warnings)


def _summarize_symbol(
    *,
    symbol: str,
    timestamps: list[datetime],
    query: BarQuery,
    interval_seconds: int | None,
    expected_bar_count: int | None,
) -> SymbolQualitySummary:
    """Build the quality summary for one symbol.

    Args:
        symbol: Canonical symbol.
        timestamps: Sorted unique observed timestamps.
        query: Normalized requested bar query.
        interval_seconds: Fixed interval seconds when the timeframe supports it.
        expected_bar_count: Expected inclusive bar count when known.

    Returns:
        Symbol quality summary.
    """
    missing_gap_count = 0
    missing_bar_count = 0
    max_gap_seconds = 0
    if interval_seconds is not None and timestamps:
        for earlier, later in zip(timestamps, timestamps[1:]):
            delta_seconds = int((later - earlier).total_seconds())
            if delta_seconds > interval_seconds:
                missing_gap_count += 1
                missing_bar_count += max((delta_seconds // interval_seconds) - 1, 1)
                max_gap_seconds = max(max_gap_seconds, delta_seconds)

    first_ts = timestamps[0] if timestamps else None
    last_ts = timestamps[-1] if timestamps else None
    bar_count = len(timestamps)
    complete = _is_complete(
        bar_count=bar_count,
        expected_bar_count=expected_bar_count,
        first_ts=first_ts,
        last_ts=last_ts,
        query=query,
        missing_gap_count=missing_gap_count,
    )
    return SymbolQualitySummary(
        symbol=symbol,
        bar_count=bar_count,
        expected_bar_count=expected_bar_count,
        first_ts=first_ts,
        last_ts=last_ts,
        missing_gap_count=missing_gap_count,
        missing_bar_count=missing_bar_count,
        expected_gap_count=0,
        session_gap_count=0,
        max_gap_seconds=max_gap_seconds,
        complete=complete,
    )


def _expected_bar_count(query: BarQuery, interval_seconds: int | None) -> int | None:
    """Return expected inclusive fixed-interval bar count.

    Args:
        query: Normalized requested bar query.
        interval_seconds: Fixed interval seconds when known.

    Returns:
        Expected bar count, or `None` for non-fixed intervals.
    """
    if interval_seconds is None:
        return None
    window_seconds = int((query.end - query.start).total_seconds())
    return (window_seconds // interval_seconds) + 1


def _is_complete(
    *,
    bar_count: int,
    expected_bar_count: int | None,
    first_ts: datetime | None,
    last_ts: datetime | None,
    query: BarQuery,
    missing_gap_count: int,
) -> bool:
    """Return whether one symbol fully covers the requested window.

    Args:
        bar_count: Observed bar count.
        expected_bar_count: Expected bar count when known.
        first_ts: First observed timestamp.
        last_ts: Last observed timestamp.
        query: Normalized requested bar query.
        missing_gap_count: Number of detected missing gaps.

    Returns:
        True when no missing data is detected.
    """
    if bar_count == 0 or first_ts is None or last_ts is None:
        return False
    if expected_bar_count is not None and bar_count != expected_bar_count:
        return False
    return first_ts <= query.start and last_ts >= query.end and missing_gap_count == 0


def _symbol_warnings(summary: SymbolQualitySummary) -> list[str]:
    """Build warnings for one symbol quality summary.

    Args:
        summary: Symbol quality summary.

    Returns:
        Warning strings for missing rows or gaps.
    """
    warnings: list[str] = []
    if summary.bar_count == 0:
        warnings.append(f"No bars found for {summary.symbol}.")
    if summary.expected_bar_count is not None and summary.bar_count < summary.expected_bar_count:
        warnings.append(
            f"{summary.symbol} has {summary.bar_count} bars but expected {summary.expected_bar_count}."
        )
    if summary.missing_gap_count:
        warnings.append(
            f"Detected {summary.missing_gap_count} missing gap(s) for {summary.symbol}."
        )
    return warnings


def _fixed_interval_seconds(timeframe: str) -> int | None:
    """Return fixed interval seconds for a normalized timeframe.

    Args:
        timeframe: Normalized timeframe string.

    Returns:
        Interval length in seconds, or `None` for variable-length intervals.
    """
    if timeframe.endswith("Min"):
        return int(timeframe.removesuffix("Min")) * 60
    if timeframe.endswith("Hour"):
        return int(timeframe.removesuffix("Hour")) * 60 * 60
    if timeframe.endswith("Day"):
        return int(timeframe.removesuffix("Day")) * 24 * 60 * 60
    if timeframe.endswith("Week"):
        return int(timeframe.removesuffix("Week")) * 7 * 24 * 60 * 60
    return None


def _report_id(query: BarQuery) -> str:
    """Build a stable data-quality report identifier.

    Args:
        query: Normalized query.

    Returns:
        Stable report identifier.
    """
    payload = {
        "symbols": list(query.symbols),
        "asset_class": query.asset_class,
        "timeframe": query.timeframe,
        "start": query.start.isoformat(),
        "end": query.end.isoformat(),
        "source": query.source,
    }
    serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(serialized.encode("utf-8")).hexdigest()[:16]
    return f"data_quality_{digest}"


@dataclass(frozen=True)
class GapRecord:
    """One timestamp discontinuity detected during bar coverage analysis.

    The record preserves adjacent timestamps, observed/expected deltas,
    threshold used for classification, and whether the gap is expected market
    session downtime or missing data that needs attention.
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

    The summary separates unexpected missing-data gaps from expected market
    session gaps so operators can prioritize remediation work.
    """

    symbol: str
    total_bars: int
    missing_gaps: int
    expected_gaps: int
    max_gap: timedelta | None


@dataclass(frozen=True)
class SessionWindow:
    """Trading-session window used to classify overnight and weekend gaps.

    Configured windows override default stock-market assumptions for symbols or
    timeframes with special trading hours.
    """

    symbol: str
    timeframe: str
    start_time: time
    end_time: time
    timezone: ZoneInfo


def run_data_quality(config_data: Mapping[str, object]) -> dict[str, object]:
    """Run configured bar-coverage checks and return a JSON-ready report.

    The function builds runtime config, reads the `data_quality` section, loads
    stored bar timestamps per symbol, classifies timestamp gaps using timeframe
    and optional session-window rules, logs summaries, and closes the event
    store before returning the structured report.
    """
    config = build_config(config_data)
    quality = _get_section(config_data, "data_quality")
    symbols = _parse_symbols(quality.get("symbols") or config.market_data_symbols)
    if not symbols:
        raise ValueError("data_quality.symbols is required")
    asset_class = str(quality.get("asset_class", config.market_data_asset_class)).lower()
    timeframe = normalize_timeframe(str(quality.get("timeframe", config.strategy_timeframe)))
    start = _parse_datetime(quality.get("start"))
    end = _parse_datetime(quality.get("end"))
    max_gap_logs = _as_int(quality.get("max_gap_logs"), 50)
    multipliers = _parse_gap_multipliers(quality.get("gap_multipliers"))
    sessions = _parse_sessions(quality.get("sessions"))

    event_store = build_event_store(config)
    summaries: list[DataQualitySummary] = []
    gaps_by_symbol: dict[str, list[GapRecord]] = {}
    try:
        for symbol in symbols:
            timestamps = _fetch_timestamps(
                event_store,
                asset_class,
                symbol,
                timeframe,
                start=start,
                end=end,
            )
            summary, gaps = _analyze_gaps(
                symbol=symbol,
                timestamps=timestamps,
                asset_class=asset_class,
                timeframe=timeframe,
                multipliers=multipliers,
                sessions=sessions,
            )
            _log_summary(summary)
            _log_gaps(gaps, max_gap_logs=max_gap_logs)
            summaries.append(summary)
            gaps_by_symbol[symbol] = gaps
    finally:
        event_store.close()
    return _build_report(
        symbols=symbols,
        asset_class=asset_class,
        timeframe=timeframe,
        start=start,
        end=end,
        summaries=summaries,
        gaps_by_symbol=gaps_by_symbol,
    )


def write_data_quality_report(report: Mapping[str, object], path: str | Path) -> Path:
    """Write a data-quality report to JSON, creating parent directories.

    Returns:
        The normalized output path after the report has been written.
    """
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    return output_path


def _fetch_timestamps(
    event_store: EventStore,
    asset_class: str,
    symbol: str,
    timeframe: str,
    *,
    start: datetime | None,
    end: datetime | None,
) -> list[datetime]:
    """Fetch stored bar timestamps for one symbol/timeframe in ascending order."""
    table = "crypto_bar_events" if asset_class in {"crypto", "cryptocurrency"} else "stock_bar_events"
    connection = getattr(event_store, "connection", lambda: None)()
    if connection is None or not hasattr(connection, "cursor"):
        logger.warning("Data quality skipped; event store has no connection")
        return []

    placeholder = _param_placeholder(connection)
    filters = [f"symbol = {placeholder}", f"COALESCE(timeframe, '1Min') = {placeholder}"]
    params: list[object] = [symbol.upper(), timeframe]
    if start is not None:
        filters.append(f"ts >= {placeholder}")
        params.append(start)
    if end is not None:
        filters.append(f"ts <= {placeholder}")
        params.append(end)
    where_clause = " AND ".join(filters)
    query = f"""
        SELECT ts
        FROM {table}
        WHERE {where_clause}
        ORDER BY ts ASC
    """
    with connection.cursor() as cursor:
        cursor.execute(query, params)
        return [_normalize_timestamp(row[0]) for row in cursor.fetchall()]


def _analyze_gaps(
    *,
    symbol: str,
    timestamps: Sequence[datetime],
    asset_class: str,
    timeframe: str,
    multipliers: Mapping[str, float],
    sessions: Mapping[tuple[str, str], SessionWindow],
) -> tuple[DataQualitySummary, list[GapRecord]]:
    """Classify oversized timestamp gaps for one symbol.

    Gaps below the timeframe-specific threshold are ignored. Larger gaps are
    split into expected session gaps and missing-data gaps so reports avoid
    treating normal market closures as data defects.
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

    expected_delta = _expected_delta(timeframe)
    unit = _timeframe_unit(timeframe)
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
        reason = _gap_reason(prev_ts, next_ts, asset_class, timeframe, session=session)
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


def _gap_reason(
    prev_ts: datetime,
    next_ts: datetime,
    asset_class: str,
    timeframe: str,
    *,
    session: SessionWindow | None,
) -> str:
    """Return the data-quality reason code for a timestamp gap."""
    if asset_class not in {"stocks", "stock"}:
        if session and _is_expected_window_gap(prev_ts, next_ts, session):
            return "expected_session_gap"
        return "gap"
    unit = _timeframe_unit(timeframe)
    if unit in {"minute", "hour"}:
        if session and _is_expected_window_gap(prev_ts, next_ts, session):
            return "expected_session_gap"
        if unit == "minute" and prev_ts.date() != next_ts.date():
            return "expected_session_gap"
        if _is_expected_session_gap(prev_ts, next_ts):
            return "expected_session_gap"
    elif unit in {"day", "week", "month"}:
        if _is_expected_daily_gap(prev_ts, next_ts, timeframe):
            return "expected_session_gap"
    return "gap"


def _is_expected_session_gap(prev_ts: datetime, next_ts: datetime) -> bool:
    """Return whether expected session gap."""
    prev_local = prev_ts.astimezone(_MARKET_TZ)
    next_local = next_ts.astimezone(_MARKET_TZ)
    if prev_local.date() == next_local.date():
        return False
    trading_days = _count_trading_days(prev_local.date(), next_local.date())
    return trading_days <= 1


def _is_expected_window_gap(prev_ts: datetime, next_ts: datetime, session: SessionWindow) -> bool:
    """Return whether expected window gap."""
    prev_local = prev_ts.astimezone(session.timezone)
    next_local = next_ts.astimezone(session.timezone)
    if prev_local.date() == next_local.date():
        return False
    if prev_local.time() < session.end_time:
        return False
    if next_local.time() > session.start_time:
        return False
    return True


def _is_expected_daily_gap(prev_ts: datetime, next_ts: datetime, timeframe: str) -> bool:
    """Return whether a day/week/month gap is normal market-calendar downtime."""
    prev_local = prev_ts.astimezone(_MARKET_TZ)
    next_local = next_ts.astimezone(_MARKET_TZ)
    trading_days = _count_trading_days(prev_local.date(), next_local.date())
    expected_days = _expected_trading_days(timeframe)
    return trading_days <= expected_days


def _expected_trading_days(timeframe: str) -> int:
    """Return the approximate trading-day span represented by a timeframe."""
    tf = normalize_timeframe(timeframe)
    amount, unit = _parse_timeframe_parts(tf)
    if unit == "week":
        return amount * 5
    if unit == "month":
        return amount * 21
    return amount


def _count_trading_days(start_date: datetime.date, end_date: datetime.date) -> int:
    """Count weekdays between two dates, excluding the start date."""
    if end_date <= start_date:
        return 0
    day = start_date + timedelta(days=1)
    count = 0
    while day <= end_date:
        if day.weekday() < 5:
            count += 1
        day += timedelta(days=1)
    return count


def _expected_delta(timeframe: str) -> timedelta:
    """Return the nominal wall-clock delta represented by one bar."""
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


def _timeframe_unit(timeframe: str) -> str:
    """Return the coarse unit name for a normalized timeframe string."""
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


def _parse_timeframe_parts(timeframe: str) -> tuple[int, str]:
    """Return numeric amount and lowercase unit from a normalized timeframe."""
    tf = normalize_timeframe(timeframe)
    for unit in ("Min", "Hour", "Day", "Week", "Month"):
        if tf.endswith(unit):
            amount = int(tf[: -len(unit)])
            return amount, unit.lower()
    raise ValueError(f"Unsupported timeframe: {timeframe}")


def _parse_symbols(value: object) -> tuple[str, ...]:
    """Parse configured symbols from a comma string or sequence."""
    if value is None:
        return tuple()
    if isinstance(value, str):
        symbols = [symbol.strip().upper() for symbol in value.split(",") if symbol.strip()]
        return tuple(symbols)
    if isinstance(value, (list, tuple)):
        symbols = [str(symbol).strip().upper() for symbol in value if str(symbol).strip()]
        return tuple(symbols)
    raise ValueError("data_quality.symbols must be a string or list")


def _parse_datetime(value: object | None) -> datetime | None:
    """Parse optional ISO datetime config values for report bounds."""
    if value in {None, ""}:
        return None
    text = str(value)
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    return datetime.fromisoformat(text)


def _parse_gap_multipliers(value: object | None) -> dict[str, float]:
    """Parse per-timeframe gap thresholds, merging with defaults."""
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


def _parse_sessions(value: object | None) -> dict[tuple[str, str], SessionWindow]:
    """Parse optional symbol/timeframe-specific trading session windows."""
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
        start_time = _parse_clock_time(str(start_raw))
        end_time = _parse_clock_time(str(end_raw))
        sessions[(symbol, timeframe)] = SessionWindow(
            symbol=symbol,
            timeframe=timeframe,
            start_time=start_time,
            end_time=end_time,
            timezone=timezone,
        )
    return sessions


def _parse_clock_time(value: str) -> time:
    """Parse `HH:MM` session-clock values into `datetime.time`."""
    parts = value.split(":")
    if len(parts) != 2:
        raise ValueError(f"Invalid time value: {value}")
    hour = int(parts[0])
    minute = int(parts[1])
    return time(hour=hour, minute=minute)


def _log_summary(summary: DataQualitySummary) -> None:
    """Emit one concise operator log line for a symbol quality summary."""
    logger.info(
        "Data quality summary symbol=%s bars=%s missing_gaps=%s expected_gaps=%s max_gap=%s",
        summary.symbol,
        summary.total_bars,
        summary.missing_gaps,
        summary.expected_gaps,
        summary.max_gap,
    )


def _log_gaps(gaps: Iterable[GapRecord], *, max_gap_logs: int) -> None:
    """Log classified gaps, suppressing noisy tails after the configured limit."""
    gap_list = list(gaps)
    for idx, gap in enumerate(gap_list):
        if idx >= max_gap_logs:
            logger.warning("Additional gaps suppressed count=%s", len(gap_list) - max_gap_logs)
            break
        if gap.reason == "expected_session_gap":
            logger.info(
                "Expected session gap symbol=%s prev_ts=%s next_ts=%s delta=%s threshold=%s",
                gap.symbol,
                gap.prev_ts.isoformat(),
                gap.next_ts.isoformat(),
                gap.delta,
                gap.threshold,
            )
            continue
        logger.warning(
            "Missing gap symbol=%s prev_ts=%s next_ts=%s delta=%s threshold=%s",
            gap.symbol,
            gap.prev_ts.isoformat(),
            gap.next_ts.isoformat(),
            gap.delta,
            gap.threshold,
        )


def _build_report(
    *,
    symbols: Sequence[str],
    asset_class: str,
    timeframe: str,
    start: datetime | None,
    end: datetime | None,
    summaries: Sequence[DataQualitySummary],
    gaps_by_symbol: Mapping[str, Sequence[GapRecord]],
) -> dict[str, object]:
    """Build a JSON-serializable data quality report."""
    summary_payload = [_summary_payload(summary) for summary in summaries]
    gap_payload = {
        symbol: [_gap_payload(gap) for gap in gaps]
        for symbol, gaps in gaps_by_symbol.items()
    }
    stable_payload = {
        "symbols": list(symbols),
        "asset_class": asset_class,
        "timeframe": timeframe,
        "start": start.isoformat() if start else None,
        "end": end.isoformat() if end else None,
        "summaries": summary_payload,
    }
    report_id = "dq_" + hashlib.sha256(
        json.dumps(stable_payload, sort_keys=True).encode("utf-8")
    ).hexdigest()[:16]
    return {
        "report_id": report_id,
        "generated_at": datetime.now(tz=ZoneInfo("UTC")).isoformat(),
        **stable_payload,
        "gaps": gap_payload,
    }


def _summary_payload(summary: DataQualitySummary) -> dict[str, object]:
    """Return a JSON-serializable legacy summary payload."""
    return {
        "symbol": summary.symbol,
        "total_bars": summary.total_bars,
        "missing_gaps": summary.missing_gaps,
        "expected_gaps": summary.expected_gaps,
        "max_gap_seconds": summary.max_gap.total_seconds() if summary.max_gap else None,
    }


def _gap_payload(gap: GapRecord) -> dict[str, object]:
    """Return a JSON-serializable gap payload."""
    return {
        "symbol": gap.symbol,
        "prev_ts": gap.prev_ts.isoformat(),
        "next_ts": gap.next_ts.isoformat(),
        "delta_seconds": gap.delta.total_seconds(),
        "expected_seconds": gap.expected.total_seconds(),
        "threshold_seconds": gap.threshold.total_seconds(),
        "reason": gap.reason,
    }


def _param_placeholder(connection: object) -> str:
    """Return the SQL parameter placeholder for the active backend."""
    module = connection.__class__.__module__
    if module.startswith("duckdb"):
        return "?"
    return "%s"


def _as_int(value: object | None, default: int) -> int:
    """Coerce a value into an integer."""
    if value is None or value == "":
        return default
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid integer value: {value}") from exc


def _get_section(data: Mapping[str, object], key: str) -> Mapping[str, object]:
    """Return a nested config section, treating missing/null as empty."""
    value = data.get(key, {})
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise ValueError(f"Config section '{key}' must be a mapping")
    return value


def _normalize_timestamp(value: datetime) -> datetime:
    """Normalize timestamp values to UTC-aware datetimes."""
    if value.tzinfo is None:
        return value.replace(tzinfo=ZoneInfo("UTC"))
    return value.astimezone(ZoneInfo("UTC"))


if __name__ == "__main__":
    raise SystemExit(
        "trader.market_data.quality is a library module. "
        "Use run_data_quality.py (external entrypoint) to run checks."
    )
