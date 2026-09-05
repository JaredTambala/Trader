"""Contracts for Postgres event-store adapter method wiring without a database.

Subject: SQL selection, parameter delegation, connection commits, and experiment-row normalization.
Level: Deterministic persistence-adapter unit contracts.
Collaborators: A partially constructed real adapter with recording connection and cursor fakes.
Guarantees: Public adapter methods use the intended statements, ordered parameters, commits, and mappings.
Non-goals: Schema creation, real Postgres semantics, transaction failures, notifications, or concurrency.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Sequence

import pytest

from trader.event_store import postgres as postgres_module
from trader.event_store.postgres import PostgresEventStore
from trader.event_store.statements import (
    LIST_EXPERIMENT_RUNS_SQL,
    RUN_SESSION_START_SQL,
    TRADING_SESSION_START_SQL,
)


class RecordingCursor:
    """Cursor fake that records query execution and returns configured rows."""

    def __init__(self, rows: Sequence[Sequence[object]]) -> None:
        self.rows = rows
        self.executed: list[tuple[object, list[object]]] = []

    def __enter__(self) -> RecordingCursor:
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        return None

    def execute(self, query: object, params: Sequence[object]) -> None:
        """Record the query and parameters used by the adapter."""
        self.executed.append((query, list(params)))

    def fetchall(self) -> Sequence[Sequence[object]]:
        """Return configured rows."""
        return self.rows


class RecordingConnection:
    """Connection fake that captures direct and cursor-backed executions."""

    def __init__(self, rows: Sequence[Sequence[object]] = ()) -> None:
        self.executed: list[tuple[object, list[object]]] = []
        self.cursor_instance = RecordingCursor(rows)

    def execute(self, query: object, params: Sequence[object] | None = None) -> None:
        """Record direct statement execution."""
        self.executed.append((query, list(params or ())))

    def cursor(self) -> RecordingCursor:
        """Return the configured cursor fake."""
        return self.cursor_instance


def _postgres_store(connection: RecordingConnection) -> PostgresEventStore:
    store = object.__new__(PostgresEventStore)
    store._connection = connection  # type: ignore[attr-defined]
    return store


def test_record_event_uses_insert_plan_and_aligned_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Ensure generic inserts execute with planned table, columns, and values."""
    connection = RecordingConnection()
    store = _postgres_store(connection)

    def fake_event_insert_query(plan: object) -> object:
        event_plan = (
            plan  # local name keeps assertions readable inside tuple construction.
        )
        return (
            "insert",
            event_plan.event_type,
            event_plan.columns,
            event_plan.ignore_bar_conflicts,
        )

    monkeypatch.setattr(postgres_module, "_event_insert_query", fake_event_insert_query)

    store.record_event(
        "stock_bar_events",
        {"symbol": "AAPL", "timeframe": "1Min", "ts": "now", "source": "test"},
    )

    assert connection.executed == [
        (
            (
                "insert",
                "stock_bar_events",
                ("symbol", "timeframe", "ts", "source"),
                True,
            ),
            ["AAPL", "1Min", "now", "test"],
        )
    ]


def test_record_event_rejects_unknown_event_type_before_sql_construction() -> None:
    """Ensure generic insert validation fails before touching the connection."""
    connection = RecordingConnection()
    store = _postgres_store(connection)

    with pytest.raises(ValueError, match="Unknown event type: unknown_events"):
        store.record_event("unknown_events", {"id": "1"})

    assert connection.executed == []


def test_record_run_session_start_uses_normalized_statement_parameters() -> None:
    """Ensure run-session writes delegate normalized parameters to both lifecycle statements."""
    timestamp = datetime(2026, 1, 21, 12, 0, tzinfo=timezone.utc)
    connection = RecordingConnection()
    store = _postgres_store(connection)

    store.record_run_session_start(
        run_id="run_1",
        run_type="trading",
        started_at=timestamp,
        strategy_id="demo",
        config_snapshot={"mode": "once"},
        mode="once",
        symbols=("AAPL",),
        timeframe="1Min",
    )

    assert connection.executed == [
        (
            RUN_SESSION_START_SQL,
            [
                "run_1",
                "trading",
                timestamp,
                "started",
                None,
                '{"mode": "once"}',
                "once",
                ["AAPL"],
                "1Min",
                None,
                None,
            ],
        ),
        (
            TRADING_SESSION_START_SQL,
            [
                "run_1",
                "demo",
                timestamp,
                "started",
                None,
                '{"mode": "once"}',
                "once",
                ["AAPL"],
                "1Min",
                None,
                None,
            ],
        ),
    ]


def test_list_experiment_runs_uses_query_plan_and_maps_rows() -> None:
    """Ensure experiment-run listing delegates query planning and row mapping."""
    row = tuple(range(21))
    connection = RecordingConnection(rows=(row,))
    store = _postgres_store(connection)

    records = store.list_experiment_runs("exp_1", limit=5)

    assert connection.cursor_instance.executed == [
        (LIST_EXPERIMENT_RUNS_SQL + " LIMIT %s", ["exp_1", 5])
    ]
    assert len(records) == 1
    assert records[0]["experiment_run_id"] == 0
    assert records[0]["error_message"] == 20
