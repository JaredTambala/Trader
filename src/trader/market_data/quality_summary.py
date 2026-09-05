"""Pure fixed-interval market-data quality summary builders."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import hashlib
import json
from typing import Any, Iterable, Mapping

from .queries import BarQuery, normalize_bar_query

__all__ = [
    "SymbolQualitySummary",
    "_expected_bar_count",
    "_fixed_interval_seconds",
    "_is_complete",
    "_report_id",
    "_summarize_symbol",
    "_symbol_warnings",
    "summarize_bar_quality_from_timestamps",
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
        """Return the summary as a JSON-compatible mapping."""
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


def summarize_bar_quality_from_timestamps(
    query: BarQuery,
    timestamps_by_symbol: Mapping[str, Iterable[datetime]],
) -> tuple[dict[str, Any], tuple[str, ...]]:
    """Summarize bar coverage from already-fetched timestamps.

    Args:
        query: Bounded market-data bar query.
        timestamps_by_symbol: Observed timestamps keyed by requested symbol.

    Returns:
        Tuple of quality report payload and non-fatal warnings.
    """
    normalized = normalize_bar_query(query)
    interval_seconds = _fixed_interval_seconds(normalized.timeframe)
    expected_bar_count = _expected_bar_count(normalized, interval_seconds)
    symbol_summaries: list[SymbolQualitySummary] = []
    warnings: list[str] = []
    for symbol in normalized.symbols:
        summary = _summarize_symbol(
            symbol=symbol,
            timestamps=sorted(set(timestamps_by_symbol.get(symbol, ()))),
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
    """Build the quality summary for one symbol."""
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
    """Return expected inclusive fixed-interval bar count."""
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
    """Return whether one symbol fully covers the requested window."""
    if bar_count == 0 or first_ts is None or last_ts is None:
        return False
    if expected_bar_count is not None and bar_count != expected_bar_count:
        return False
    return first_ts <= query.start and last_ts >= query.end and missing_gap_count == 0


def _symbol_warnings(summary: SymbolQualitySummary) -> list[str]:
    """Build warnings for one symbol quality summary."""
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
    """Return fixed interval seconds for a normalized timeframe."""
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
    """Build a stable data-quality report identifier."""
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
