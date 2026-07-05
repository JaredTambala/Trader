"""Event-store persistence helpers for backtest results and fill accounting."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from typing import Sequence

from ..config import Config
from ..event_store import EventStore, build_event_store
from .data import _normalize_timestamp
from .exports import serialize_backtest_result
from .models import BacktestResult, EquityPoint, TradeStats as _TradeStats
from .performance import (
    _compute_trade_stats_from_events,
    _normalize_fill_accounting_events,
    _normalize_order_accounting_events,
)


def _compute_trade_stats(
    event_store: EventStore,
    run_id: str,
    equity_curve: Sequence[EquityPoint],
) -> _TradeStats | None:
    """Load fill evidence and compute trade-level statistics."""
    connection = getattr(event_store, "connection", lambda: None)()
    if connection is None or not hasattr(connection, "cursor"):
        return None

    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT client_order_id, symbol, side, cycle_id
            FROM order_events
            WHERE run_id = %s AND client_order_id IS NOT NULL AND side IS NOT NULL
            """,
            [run_id],
        )
        order_rows = cursor.fetchall()

        cursor.execute(
            """
            SELECT client_order_id, fill_ts, fill_qty, fill_price, raw_fill_price, fee_amount, slippage_amount
            FROM fill_events
            WHERE run_id = %s
            ORDER BY fill_ts ASC
            """,
            [run_id],
        )
        fill_rows = cursor.fetchall()

    return _compute_trade_stats_from_events(
        order_events=_normalize_order_accounting_events(order_rows),
        fill_events=_normalize_fill_accounting_events(fill_rows),
        equity_curve=equity_curve,
    )


def _build_backtest_metrics_snapshot_payload(
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


def persist_backtest_result(run_id: str, result: BacktestResult, config: Config) -> None:
    """Persist a serialized backtest result as a metrics snapshot.

    A fresh event store is built from config for the write and always closed
    afterward. The snapshot is keyed by `run_id`/`session_id` with no cycle ID
    because it represents the aggregate run outcome rather than one decision.
    """
    event_store = build_event_store(config)
    try:
        event_store.record_event(
            "metrics_snapshots",
            _build_backtest_metrics_snapshot_payload(
                run_id=run_id,
                result=result,
                ts=datetime.now(timezone.utc),
            ),
        )
    finally:
        event_store.close()
