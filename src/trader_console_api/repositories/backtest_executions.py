"""Scoped persistence for durable Console backtest execution commands."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from pydantic import ValidationError
from psycopg.types.json import Jsonb

from ..contracts import BacktestDefinition, BacktestExecutionRecord
from .backtest_executions_schema import (
    CATALOG_SQL,
    COLUMNS,
    BacktestExecutionStorageUnavailable,
)
from .database import ConsoleDatabase
from .resources import _row_dicts


class BacktestExecutionNotFound(RuntimeError):
    """The requested execution command is absent from the configured scope."""


class BacktestExecutionDefinitionNotFound(RuntimeError):
    """The definition revision selected for execution is absent."""


def _stored(cursor: Any, rows: list[Any]) -> list[BacktestExecutionRecord]:
    try:
        records = _row_dicts(cursor, rows)
        for record in records:
            record["execution_id"] = str(record["execution_id"])
            record["definition_id"] = str(record["definition_id"])
        return [BacktestExecutionRecord.model_validate(row) for row in records]
    except ValidationError as exc:
        raise BacktestExecutionStorageUnavailable(
            "Stored backtest execution format is incompatible"
        ) from exc


class BacktestExecutionSession:
    """One transaction bound to a server-owned scope."""

    def __init__(self, connection: Any, scope_id: str) -> None:
        """Bind trusted scope identity to command SQL."""
        self._connection = connection
        self._scope_id = scope_id

    async def require_storage(self) -> None:
        """Refuse absent or incompatible storage without creating relations."""
        cursor = await self._connection.execute(CATALOG_SQL)
        if dict(await cursor.fetchall()) != COLUMNS:
            raise BacktestExecutionStorageUnavailable(
                "Install Console backtest execution storage explicitly"
            )

    async def submit(
        self,
        definition_id: UUID,
        *,
        idempotency_key: str,
    ) -> BacktestExecutionRecord:
        """Create one queued command or return the existing idempotent command."""
        cursor = await self._connection.execute(
            "SELECT definition_id, revision, fingerprint "
            "FROM console_app.backtest_definitions "
            "WHERE scope_id = %s AND definition_id = %s "
            "ORDER BY revision DESC LIMIT 1",
            [self._scope_id, definition_id],
        )
        definition_rows = await cursor.fetchall()
        if not definition_rows:
            raise BacktestExecutionDefinitionNotFound("Backtest definition not found")
        _definition_uuid, revision, fingerprint = definition_rows[0]
        cursor = await self._connection.execute(
            "INSERT INTO console_app.backtest_executions "
            "(scope_id, execution_id, definition_id, definition_revision, definition_fingerprint, "
            "idempotency_key, status, attempt, processed_cycles, warning_summary) "
            "VALUES (%s, %s, %s, %s, %s, %s, 'queued', 0, 0, %s) "
            "ON CONFLICT (scope_id, idempotency_key) DO NOTHING RETURNING *",
            [
                self._scope_id,
                uuid4(),
                definition_id,
                revision,
                fingerprint,
                idempotency_key,
                Jsonb([]),
            ],
        )
        rows = await cursor.fetchall()
        if rows:
            return _stored(cursor, rows)[0]
        cursor = await self._connection.execute(
            "SELECT * FROM console_app.backtest_executions "
            "WHERE scope_id = %s AND idempotency_key = %s",
            [self._scope_id, idempotency_key],
        )
        existing = _stored(cursor, await cursor.fetchall())
        if not existing:
            raise BacktestExecutionNotFound("Execution command was not available after submit")
        return existing[0]

    async def claim_next(
        self,
        *,
        worker_id: str,
        lease_seconds: int,
        max_attempts: int,
    ) -> BacktestExecutionRecord | None:
        """Reconcile ambiguous leases, then claim one bounded-retry command."""
        await self._connection.execute(
            "UPDATE console_app.backtest_executions SET status = 'reconciliation_required', "
            "terminal_error_code = 'worker_lease_expired', "
            "terminal_error_message = 'A worker lease expired after a producer run was reserved', "
            "finished_at = transaction_timestamp(), lease_expires_at = NULL "
            "WHERE scope_id = %s AND status = 'running' AND lease_expires_at < transaction_timestamp() "
            "AND run_id IS NOT NULL",
            [self._scope_id],
        )
        await self._connection.execute(
            "UPDATE console_app.backtest_executions SET status = 'reconciliation_required', "
            "terminal_error_code = 'lease_retry_exhausted', "
            "terminal_error_message = 'Worker lease retries were exhausted before a run was reserved', "
            "finished_at = transaction_timestamp(), lease_expires_at = NULL "
            "WHERE scope_id = %s AND status = 'running' AND lease_expires_at < transaction_timestamp() "
            "AND run_id IS NULL AND attempt >= %s",
            [self._scope_id, max_attempts],
        )
        cursor = await self._connection.execute(
            "WITH candidate AS ("
            "SELECT execution_id FROM console_app.backtest_executions "
            "WHERE scope_id = %s AND (status = 'queued' OR "
            "(status = 'running' AND lease_expires_at < transaction_timestamp() AND run_id IS NULL AND attempt < %s)) "
            "ORDER BY created_at, execution_id LIMIT 1 FOR UPDATE SKIP LOCKED"
            ") UPDATE console_app.backtest_executions AS command "
            "SET status = 'running', worker_id = %s, attempt = command.attempt + 1, "
            "started_at = COALESCE(command.started_at, transaction_timestamp()), "
            "heartbeat_at = transaction_timestamp(), "
            "lease_expires_at = transaction_timestamp() + (%s * interval '1 second') "
            "FROM candidate WHERE command.scope_id = %s AND command.execution_id = candidate.execution_id "
            "RETURNING command.*",
            [self._scope_id, max_attempts, worker_id, lease_seconds, self._scope_id],
        )
        rows = _stored(cursor, await cursor.fetchall())
        return rows[0] if rows else None

    async def load_definition(
        self,
        definition_id: UUID,
        revision: int,
    ) -> BacktestDefinition | None:
        """Load the exact immutable definition revision selected by a command."""
        cursor = await self._connection.execute(
            "SELECT definition FROM console_app.backtest_definitions "
            "WHERE scope_id = %s AND definition_id = %s AND revision = %s",
            [self._scope_id, definition_id, revision],
        )
        rows = await cursor.fetchall()
        if not rows:
            return None
        value = rows[0][0]
        return BacktestDefinition.model_validate(value)

    async def reserve_run_id(
        self,
        execution_id: UUID,
        *,
        worker_id: str,
        run_id: str,
    ) -> bool:
        """Persist the deterministic producer run identity while the lease is held."""
        cursor = await self._connection.execute(
            "UPDATE console_app.backtest_executions SET run_id = %s "
            "WHERE scope_id = %s AND execution_id = %s AND status = 'running' AND worker_id = %s "
            "AND run_id IS NULL RETURNING execution_id",
            [run_id, self._scope_id, execution_id, worker_id],
        )
        return bool(await cursor.fetchall())

    async def heartbeat(
        self,
        execution_id: UUID,
        *,
        worker_id: str,
        processed_cycles: int,
        total_cycles: int | None,
        last_decision_at: datetime | None,
        lease_seconds: int,
    ) -> bool:
        """Extend a worker lease and persist coarse replay progress."""
        cursor = await self._connection.execute(
            "UPDATE console_app.backtest_executions SET processed_cycles = %s, total_cycles = %s, "
            "last_decision_at = %s, heartbeat_at = transaction_timestamp(), "
            "lease_expires_at = transaction_timestamp() + (%s * interval '1 second') "
            "WHERE scope_id = %s AND execution_id = %s AND status = 'running' AND worker_id = %s "
            "RETURNING execution_id",
            [processed_cycles, total_cycles, last_decision_at, lease_seconds, self._scope_id, execution_id, worker_id],
        )
        return bool(await cursor.fetchall())

    async def finish(
        self,
        execution_id: UUID,
        *,
        worker_id: str,
        status: str,
        run_id: str | None,
        processed_cycles: int,
        total_cycles: int | None,
        warning_summary: list[str],
        error_code: str | None = None,
        error_message: str | None = None,
    ) -> bool:
        """Record one terminal outcome only while the worker still owns the lease."""
        cursor = await self._connection.execute(
            "UPDATE console_app.backtest_executions SET status = %s, run_id = COALESCE(%s, run_id), "
            "processed_cycles = %s, total_cycles = %s, warning_summary = %s, "
            "terminal_error_code = %s, terminal_error_message = %s, finished_at = transaction_timestamp(), "
            "heartbeat_at = transaction_timestamp(), lease_expires_at = NULL "
            "WHERE scope_id = %s AND execution_id = %s AND status = 'running' AND worker_id = %s "
            "RETURNING execution_id",
            [
                status, run_id, processed_cycles, total_cycles, Jsonb(warning_summary),
                error_code, error_message, self._scope_id, execution_id, worker_id,
            ],
        )
        return bool(await cursor.fetchall())

    async def get(self, execution_id: UUID) -> BacktestExecutionRecord | None:
        """Load one execution command inside the configured scope."""
        cursor = await self._connection.execute(
            "SELECT * FROM console_app.backtest_executions "
            "WHERE scope_id = %s AND execution_id = %s",
            [self._scope_id, execution_id],
        )
        rows = _stored(cursor, await cursor.fetchall())
        return rows[0] if rows else None

    async def list(self, limit: int, offset: int) -> tuple[list[BacktestExecutionRecord], int]:
        """Return bounded command history for the configured scope."""
        cursor = await self._connection.execute(
            "SELECT count(*) FROM console_app.backtest_executions WHERE scope_id = %s",
            [self._scope_id],
        )
        total = int((await cursor.fetchone())[0])
        cursor = await self._connection.execute(
            "SELECT * FROM console_app.backtest_executions "
            "WHERE scope_id = %s ORDER BY created_at DESC, execution_id LIMIT %s OFFSET %s",
            [self._scope_id, limit, offset],
        )
        return _stored(cursor, await cursor.fetchall()), total


class BacktestExecutionRepository:
    """Keep command persistence separate from producer evidence writes."""

    def __init__(self, database: ConsoleDatabase, scope_id: str) -> None:
        """Bind commands to the configured process scope."""
        self._database = database
        self._scope_id = scope_id

    @asynccontextmanager
    async def session(self, *, write: bool = False) -> AsyncIterator[BacktestExecutionSession]:
        """Yield one read or command transaction."""
        transaction = self._database.command_transaction if write else self._database.transaction
        async with transaction() as connection:
            yield BacktestExecutionSession(connection, self._scope_id)


__all__ = [
    "BacktestExecutionDefinitionNotFound",
    "BacktestExecutionNotFound",
    "BacktestExecutionRepository",
    "BacktestExecutionSession",
]
