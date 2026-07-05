"""Pure order-state query and row-shaping helpers for decision cycles."""

from __future__ import annotations

from typing import Mapping, Sequence


def _latest_order_events_query() -> str:
    """Return the query used to load latest order lifecycle rows."""
    return (
        "SELECT client_order_id, run_id, cycle_id, symbol, side, qty, order_type, "
        "status, broker_order_id, created_at "
        "FROM order_events ORDER BY created_at DESC, order_event_id DESC"
    )


def _latest_order_event_row_to_record(row: Sequence[object]) -> Mapping[str, object]:
    """Convert one order-event row into a risk-context record."""
    return {
        "client_order_id": row[0],
        "run_id": row[1],
        "cycle_id": row[2],
        "symbol": row[3],
        "side": row[4],
        "qty": row[5],
        "order_type": row[6],
        "status": row[7],
        "broker_order_id": row[8],
        "created_at": row[9],
    }


def _dedupe_latest_order_event_rows(
    rows: Sequence[Sequence[object]],
) -> tuple[Mapping[str, object], ...]:
    """Return one newest order-event record per client order ID."""
    seen: set[str] = set()
    latest: list[Mapping[str, object]] = []
    for row in rows:
        client_order_id = row[0]
        if not client_order_id:
            continue
        client_order_key = str(client_order_id)
        if client_order_key in seen:
            continue
        seen.add(client_order_key)
        latest.append(_latest_order_event_row_to_record(row))
    return tuple(latest)


__all__ = [
    "_dedupe_latest_order_event_rows",
    "_latest_order_event_row_to_record",
    "_latest_order_events_query",
]
