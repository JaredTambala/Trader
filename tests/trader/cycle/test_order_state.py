"""Cycle open-order query and normalization contracts.

Subject: Latest lifecycle-event query projection and per-client-order deduplication.
Level: Pure event-store boundary unit contracts.
Collaborators: Real order-state query builders with fixed database-shaped rows.
Guarantees: Ordered rows become one newest canonical event per valid client identifier.
Non-goals: Executing queries, broker reconciliation, risk evaluation, or event writes.
"""

from __future__ import annotations

from datetime import datetime, timezone

from trader.cycle.order_state import (
    _dedupe_latest_order_event_rows,
    _latest_order_event_row_to_record,
    _latest_order_events_query,
)


def test_latest_order_events_query_selects_lifecycle_fields_in_order() -> None:
    """Pin the lifecycle projection and newest-first ordering required by cycle risk."""
    query = _latest_order_events_query()

    assert (
        "SELECT client_order_id, run_id, cycle_id, symbol, side, qty, order_type"
        in query
    )
    assert "FROM order_events" in query
    assert "ORDER BY created_at DESC, order_event_id DESC" in query


def test_latest_order_event_row_helpers_normalize_and_dedupe_rows() -> None:
    """Keep one newest canonical row per valid client order identifier."""
    created_new = datetime(2026, 1, 20, 12, 1, tzinfo=timezone.utc)
    created_old = datetime(2026, 1, 20, 12, 0, tzinfo=timezone.utc)
    newest = (
        "cid_1",
        "run_1",
        "cycle_1",
        "AAPL",
        "buy",
        1.0,
        "market",
        "submitted",
        "broker_1",
        created_new,
    )
    older_duplicate = (
        "cid_1",
        "run_1",
        "cycle_0",
        "AAPL",
        "buy",
        1.0,
        "market",
        "created",
        None,
        created_old,
    )
    second_order = (
        "cid_2",
        "run_1",
        "cycle_1",
        "MSFT",
        "sell",
        2.0,
        "market",
        "filled",
        "broker_2",
        created_new,
    )

    assert _latest_order_event_row_to_record(newest) == {
        "client_order_id": "cid_1",
        "run_id": "run_1",
        "cycle_id": "cycle_1",
        "symbol": "AAPL",
        "side": "buy",
        "qty": 1.0,
        "order_type": "market",
        "status": "submitted",
        "broker_order_id": "broker_1",
        "created_at": created_new,
    }
    assert _dedupe_latest_order_event_rows(
        [
            newest,
            older_duplicate,
            (
                None,
                "run_1",
                "cycle_1",
                "NVDA",
                "buy",
                1.0,
                "market",
                "created",
                None,
                created_new,
            ),
            second_order,
        ]
    ) == (
        _latest_order_event_row_to_record(newest),
        _latest_order_event_row_to_record(second_order),
    )
