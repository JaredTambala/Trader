"""Typed market-data quality summaries over core market-data queries."""

from __future__ import annotations

from datetime import datetime
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
from .quality_summary import (
    SymbolQualitySummary,
    _expected_bar_count as _expected_bar_count,
    _fixed_interval_seconds as _fixed_interval_seconds,
    _is_complete as _is_complete,
    _report_id as _report_id,
    _summarize_symbol as _summarize_symbol,
    _symbol_warnings as _symbol_warnings,
    summarize_bar_quality_from_timestamps,
)


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

    return summarize_bar_quality_from_timestamps(normalized, timestamps_by_symbol)


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
