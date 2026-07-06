"""Pure payload builders for persisted backtest evidence."""

from __future__ import annotations

from datetime import datetime
import json

from .data import _normalize_timestamp
from .export_payloads import serialize_backtest_result
from .models import BacktestResult

__all__ = ["build_backtest_metrics_snapshot_payload"]


def build_backtest_metrics_snapshot_payload(
    *,
    run_id: str,
    result: BacktestResult,
    ts: datetime,
) -> dict[str, object]:
    """Build the aggregate metrics-snapshot event payload for a backtest result."""
    return {
        "ts": _normalize_timestamp(ts),
        "run_id": run_id,
        "session_id": run_id,
        "cycle_id": None,
        "payload": json.dumps(serialize_backtest_result(result)),
    }
