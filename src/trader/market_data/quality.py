"""Typed market-data quality summaries over core market-data queries."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import hashlib
import json
import logging
from pathlib import Path
from typing import Any, Iterable, Mapping
from zoneinfo import ZoneInfo

from ..config import build_config
from ..event_store import EventStore, build_event_store
from ..timeframes import normalize_timeframe
from .queries import BarQuery, fetch_bar_timestamps, normalize_bar_query
from .quality_config import (
    as_int as _as_int,
    get_section as _get_section,
    parse_datetime as _parse_datetime,
    parse_gap_multipliers as _parse_gap_multipliers,
    parse_sessions as _parse_sessions,
    parse_symbols as _parse_symbols,
)
from .quality_gaps import (
    DataQualitySummary,
    GapRecord,
    SessionWindow,
    analyze_gaps as _analyze_gaps,
)
from .quality_reports import build_quality_report as _build_report


logger = logging.getLogger(__name__)

__all__ = [
    "DataQualitySummary",
    "GapRecord",
    "SessionWindow",
    "SymbolQualitySummary",
    "run_data_quality",
    "summarize_bar_quality",
    "write_data_quality_report",
]


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
        generated_at=datetime.now(tz=ZoneInfo("UTC")),
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


def _param_placeholder(connection: object) -> str:
    """Return the SQL parameter placeholder for the active backend."""
    module = connection.__class__.__module__
    if module.startswith("duckdb"):
        return "?"
    return "%s"


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
