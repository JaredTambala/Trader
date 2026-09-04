"""Contracts for snapshot event records and backend-aware latest-state queries.

Subject: Cash sentinels, position events, lineage, deterministic ordering, placeholders, and optional bounds.
Level: Pure event-record and query-planning unit contracts.
Collaborators: Real snapshot helpers, fixed position inputs, and minimal DuckDB or Postgres connection fakes.
Guarantees: Snapshot evidence remains reconstructable and query plans match the active DB-API placeholder style.
Non-goals: Executing queries, recording events, transaction behavior, row reconstruction, or broker state.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from trader.portfolio.snapshots import (
    build_position_snapshot_events,
    latest_cash_query_plan,
    latest_positions_query_plan,
)


@dataclass(frozen=True)
class PositionInput:
    """Minimal position input used by snapshot helper tests."""

    symbol: str
    qty: float
    avg_price: float | None


class DuckConnection:
    """Connection fake with a DuckDB-style module for placeholder detection."""


DuckConnection.__module__ = "duckdb"


class PostgresConnection:
    """Connection fake with a non-DuckDB module for placeholder detection."""


def test_build_position_snapshot_events_emits_cash_only_sentinel() -> None:
    """Ensure empty portfolios still persist reconstructable cash state."""
    timestamp = datetime(2026, 1, 21, 12, 0, tzinfo=timezone.utc)

    events = build_position_snapshot_events(
        asof_ts=timestamp,
        positions=(),
        cash_balance=1000.0,
        run_id="run_1",
        cycle_id="cycle_1",
        session_id=None,
    )

    assert len(events) == 1
    assert events[0].event_type == "position_snapshots"
    assert events[0].payload == {
        "asof_ts": timestamp,
        "symbol": None,
        "qty": 0.0,
        "avg_price": None,
        "cash_balance": 1000.0,
        "run_id": "run_1",
        "cycle_id": "cycle_1",
        "session_id": "run_1",
    }


def test_build_position_snapshot_events_emits_one_record_per_position() -> None:
    """Ensure each supplied position becomes one event with shared snapshot lineage."""
    timestamp = datetime(2026, 1, 21, 12, 0, tzinfo=timezone.utc)

    events = build_position_snapshot_events(
        asof_ts=timestamp,
        positions=(
            PositionInput("AAPL", 2.0, 100.0),
            PositionInput("MSFT", -1.0, 250.0),
        ),
        cash_balance=500.0,
        run_id="run_1",
        cycle_id="cycle_1",
        session_id="session_1",
    )

    assert [event.event_type for event in events] == [
        "position_snapshots",
        "position_snapshots",
    ]
    assert events[0].payload["symbol"] == "AAPL"
    assert events[0].payload["qty"] == 2.0
    assert events[0].payload["session_id"] == "session_1"
    assert events[1].payload["symbol"] == "MSFT"
    assert events[1].payload["qty"] == -1.0


def test_latest_positions_query_plan_uses_backend_placeholder() -> None:
    """Ensure bounded position queries choose the active DB-API placeholder."""
    timestamp = datetime(2026, 1, 21, 12, 0, tzinfo=timezone.utc)

    duck_plan = latest_positions_query_plan(DuckConnection(), asof_ts=timestamp)
    postgres_plan = latest_positions_query_plan(PostgresConnection(), asof_ts=timestamp)

    assert "asof_ts <= ?" in duck_plan.query
    assert duck_plan.parameters == (timestamp,)
    assert "asof_ts <= %s" in postgres_plan.query
    assert postgres_plan.parameters == (timestamp,)


def test_latest_cash_query_plan_omits_params_when_unbounded() -> None:
    """Ensure unbounded latest-cash queries omit both timestamp predicates and parameters."""
    plan = latest_cash_query_plan(PostgresConnection())

    assert "SELECT cash_balance" in plan.query
    assert "WHERE asof_ts" not in plan.query
    assert plan.parameters == ()
