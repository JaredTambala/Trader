"""Durable execution-command repository contracts.

Subject: Idempotent submit, scope binding, and bounded command-status reads.
Level: In-process repository adapter.
Collaborators: Recording asynchronous connection; no PostgreSQL server.
Guarantees: Definition identity is snapshotted, duplicate idempotency keys return one command, and SQL values stay parameters.
Non-goals: Worker claims, lease expiry, PostgreSQL locking, and producer execution.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

from psycopg.types.json import Jsonb

from trader_console_api.repositories.backtest_executions import BacktestExecutionSession


class _Cursor:
    """Async cursor supporting definition tuples and named command rows."""

    def __init__(self, rows: list[tuple[object, ...]], names: tuple[str, ...] = ()) -> None:
        self.rows = rows
        self.description = [SimpleNamespace(name=name) for name in names]

    async def fetchall(self) -> list[tuple[object, ...]]:
        """Return configured rows."""
        return self.rows

    async def fetchone(self) -> tuple[int] | None:
        """Return no aggregate row unless configured by the connection."""
        return None


def _command_row(definition_id, execution_id, *, revision: int = 1) -> dict[str, object]:
    """Return one stored command row."""
    now = datetime(2026, 1, 1, tzinfo=UTC)
    return {
        "scope_id": "scope-a", "execution_id": execution_id, "definition_id": definition_id,
        "definition_revision": revision, "definition_fingerprint": "a" * 64,
        "idempotency_key": "submit-1", "status": "queued", "attempt": 0, "run_id": None,
        "processed_cycles": 0, "total_cycles": None, "last_decision_at": None,
        "heartbeat_at": None, "lease_expires_at": None, "created_at": now, "started_at": None,
        "finished_at": None, "warning_summary": [], "terminal_error_code": None,
        "terminal_error_message": None,
    }


class _Connection:
    """Connection double for idempotent submit and status reads."""

    def __init__(self, definition_id, command_row: dict[str, object]) -> None:
        self.definition_id = definition_id
        self.command_row = command_row
        self.calls: list[tuple[str, object | None]] = []

    async def execute(self, query: str, parameters: object | None = None) -> _Cursor:
        """Record parameterized SQL and return deterministic results."""
        self.calls.append((query, parameters))
        if "FROM console_app.backtest_definitions" in query:
            return _Cursor([(self.definition_id, 1, "a" * 64)])
        names = tuple(self.command_row)
        values = tuple(self.command_row.values())
        return _Cursor([values], names)


def test_submit_snapshots_latest_definition_and_returns_command() -> None:
    """Submit binds one queued command to the latest definition revision and server scope."""
    definition_id = uuid4()
    execution_id = uuid4()
    connection = _Connection(definition_id, _command_row(definition_id, execution_id))
    session = BacktestExecutionSession(connection, "scope-a")

    result = asyncio.run(session.submit(definition_id, idempotency_key="submit-1"))

    assert result.status == "queued"
    assert result.definition_id == str(definition_id)
    insert_query, insert_params = connection.calls[1]
    assert "ON CONFLICT (scope_id, idempotency_key) DO NOTHING" in insert_query
    assert insert_params[0] == "scope-a"
    assert "submit-1" not in insert_query


def test_get_keeps_execution_scope_in_sql_predicate() -> None:
    """Status lookup cannot cross the server-owned scope boundary."""
    definition_id = uuid4()
    execution_id = uuid4()
    connection = _Connection(definition_id, _command_row(definition_id, execution_id))
    session = BacktestExecutionSession(connection, "scope-a")

    result = asyncio.run(session.get(execution_id))

    assert result is not None
    query, parameters = connection.calls[0]
    assert "scope_id = %s" in query
    assert parameters == ["scope-a", execution_id]


def test_claim_reconciles_reserved_leases_and_bounds_unreserved_retries() -> None:
    """Worker claim marks ambiguous leases and passes a finite retry bound to SQL."""
    definition_id = uuid4()
    execution_id = uuid4()
    connection = _Connection(definition_id, _command_row(definition_id, execution_id))
    session = BacktestExecutionSession(connection, "scope-a")

    claimed = asyncio.run(
        session.claim_next(worker_id="worker-a", lease_seconds=30, max_attempts=3)
    )

    assert claimed is not None
    assert "reconciliation_required" in connection.calls[0][0]
    claim_query, claim_parameters = connection.calls[2]
    assert "SKIP LOCKED" in claim_query
    assert claim_parameters[1] == 3


def test_terminal_warning_summary_is_bound_as_json_array() -> None:
    """Terminal warning summaries use PostgreSQL JSONB array adaptation."""
    definition_id = uuid4()
    execution_id = uuid4()
    connection = _Connection(definition_id, _command_row(definition_id, execution_id))
    session = BacktestExecutionSession(connection, "scope-a")

    asyncio.run(
        session.finish(
            execution_id,
            worker_id="worker-a",
            status="completed",
            run_id="run-a",
            processed_cycles=2,
            total_cycles=2,
            warning_summary=["price_carry_forward_enabled"],
        )
    )

    parameters = connection.calls[0][1]
    assert isinstance(parameters[4], Jsonb)
    assert parameters[4].obj == ["price_carry_forward_enabled"]
