"""Report serialization helpers for market-data quality checks."""

from __future__ import annotations

from datetime import datetime
import hashlib
import json
from typing import Mapping, Sequence

from .quality_gaps import DataQualitySummary, GapRecord


def build_quality_report(
    *,
    symbols: Sequence[str],
    asset_class: str,
    timeframe: str,
    start: datetime | None,
    end: datetime | None,
    summaries: Sequence[DataQualitySummary],
    gaps_by_symbol: Mapping[str, Sequence[GapRecord]],
    generated_at: datetime,
) -> dict[str, object]:
    """Build a JSON-serializable data-quality report.

    Args:
        symbols: Requested symbols.
        asset_class: Requested asset class.
        timeframe: Requested timeframe.
        start: Optional lower timestamp bound.
        end: Optional upper timestamp bound.
        summaries: Per-symbol quality summaries.
        gaps_by_symbol: Gap records keyed by symbol.
        generated_at: Explicit report timestamp supplied by the shell.

    Returns:
        JSON-compatible report payload with a deterministic report id.
    """
    summary_payload = [summary_payload_from(summary) for summary in summaries]
    gap_payload = {
        symbol: [gap_payload_from(gap) for gap in gaps]
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
        "generated_at": generated_at.isoformat(),
        **stable_payload,
        "gaps": gap_payload,
    }


def summary_payload_from(summary: DataQualitySummary) -> dict[str, object]:
    """Return a JSON-serializable summary payload.

    Args:
        summary: Data-quality summary to serialize.

    Returns:
        JSON-compatible summary mapping.
    """
    return {
        "symbol": summary.symbol,
        "total_bars": summary.total_bars,
        "missing_gaps": summary.missing_gaps,
        "expected_gaps": summary.expected_gaps,
        "max_gap_seconds": summary.max_gap.total_seconds() if summary.max_gap else None,
    }


def gap_payload_from(gap: GapRecord) -> dict[str, object]:
    """Return a JSON-serializable gap payload.

    Args:
        gap: Gap record to serialize.

    Returns:
        JSON-compatible gap mapping.
    """
    return {
        "symbol": gap.symbol,
        "prev_ts": gap.prev_ts.isoformat(),
        "next_ts": gap.next_ts.isoformat(),
        "delta_seconds": gap.delta.total_seconds(),
        "expected_seconds": gap.expected.total_seconds(),
        "threshold_seconds": gap.threshold.total_seconds(),
        "reason": gap.reason,
    }
