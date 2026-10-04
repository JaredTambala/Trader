"""Scoped persistence for user-authored definitions and read-only run admission."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any
from uuid import UUID, uuid4

import psycopg
from psycopg.types.json import Jsonb
from pydantic import ValidationError

from ..comparison_contracts import ComparisonViewDefinition, SavedComparisonView
from .comparison_schema import CATALOG_SQL, COLUMNS, ComparisonStorageUnavailable
from .database import ConsoleDatabase, ConsoleDatabaseUnavailable
from .resources import _row_dicts


class ComparisonRevisionConflict(RuntimeError):
    """An edit raced another writer; reload the saved definition before retrying."""


@dataclass(frozen=True)
class ComparisonCandidate:
    """Published admission evidence for one run inside the selected experiment."""

    run_id: str
    scope_fingerprint: str | None
    projection_available: bool


def _saved(cursor: Any, rows: list[Any]) -> list[SavedComparisonView]:
    try:
        return [SavedComparisonView.model_validate(row) for row in _row_dicts(cursor, rows)]
    except ValidationError as exc:
        raise ComparisonStorageUnavailable("Stored definition format is incompatible") from exc


class ComparisonViewSession:
    """One transaction bound to a server-owned scope and a single experiment."""

    def __init__(self, connection: Any, scope_id: str, experiment_id: str) -> None:
        """Bind trusted scope and validated route identity to all SQL parameters."""
        self._connection = connection
        self._scope_id = scope_id
        self._experiment_id = experiment_id

    async def require_storage(self) -> None:
        """Refuse absent or incompatible storage without creating any relations."""
        cursor = await self._connection.execute(CATALOG_SQL)
        if dict(await cursor.fetchall()) != COLUMNS:
            raise ComparisonStorageUnavailable("Install Console comparison storage explicitly")

    async def experiment_exists(self) -> bool:
        """Use published run membership as the existing experiment identity source."""
        cursor = await self._connection.execute(
            "SELECT 1 FROM console_read.backtest_runs WHERE experiment_id = %s LIMIT 1",
            [self._experiment_id],
        )
        return await cursor.fetchone() is not None

    async def candidates(self, run_ids: tuple[str, ...]) -> dict[str, ComparisonCandidate]:
        """Read only selected IDs, preserving experiment membership and unknown scope."""
        if not run_ids:
            return {}
        cursor = await self._connection.execute(
            """
            SELECT runs.run_id, scope.scope_fingerprint,
                EXISTS (SELECT 1 FROM console_read.backtest_comparison_runs comparison
                        WHERE comparison.run_id = runs.run_id
                          AND comparison.experiment_id = runs.experiment_id) AS projection_available
            FROM console_read.backtest_runs runs
            LEFT JOIN console_read.backtest_scope scope
              ON scope.run_id = runs.run_id AND scope.experiment_id = runs.experiment_id
            WHERE runs.experiment_id = %s AND runs.run_id = ANY(%s)
            """,
            [self._experiment_id, list(run_ids)],
        )
        return {
            str(run_id): ComparisonCandidate(str(run_id), fingerprint, bool(available))
            for run_id, fingerprint, available in await cursor.fetchall()
        }

    async def get(self, view_id: UUID) -> SavedComparisonView | None:
        """Load a definition only within this scope and experiment."""
        cursor = await self._connection.execute(
            "SELECT * FROM console_app.comparison_views "
            "WHERE scope_id = %s AND experiment_id = %s AND view_id = %s",
            [self._scope_id, self._experiment_id, view_id],
        )
        rows = _saved(cursor, await cursor.fetchall())
        return rows[0] if rows else None

    async def list(self, limit: int, offset: int) -> tuple[list[SavedComparisonView], int]:
        """Return bounded definitions and an accurate total even past the last page."""
        cursor = await self._connection.execute(
            "SELECT count(*) FROM console_app.comparison_views WHERE scope_id = %s AND experiment_id = %s",
            [self._scope_id, self._experiment_id],
        )
        total = int((await cursor.fetchone())[0])
        cursor = await self._connection.execute(
            "SELECT * FROM console_app.comparison_views WHERE scope_id = %s AND experiment_id = %s "
            "ORDER BY updated_at DESC, view_id LIMIT %s OFFSET %s",
            [self._scope_id, self._experiment_id, limit, offset],
        )
        return _saved(cursor, await cursor.fetchall()), total

    async def save(
        self, definition: ComparisonViewDefinition, *, view_id: UUID | None = None,
        expected_revision: int | None = None,
    ) -> SavedComparisonView:
        """Insert a new definition or atomically replace the expected revision only."""
        document = Jsonb(definition.model_dump(mode="json"))
        if view_id is None:
            cursor = await self._connection.execute(
                "INSERT INTO console_app.comparison_views (scope_id, experiment_id, view_id, definition) "
                "VALUES (%s, %s, %s, %s) RETURNING *",
                [self._scope_id, self._experiment_id, uuid4(), document],
            )
        else:
            cursor = await self._connection.execute(
                "UPDATE console_app.comparison_views SET definition = %s, revision = revision + 1, "
                "updated_at = transaction_timestamp() "
                "WHERE scope_id = %s AND experiment_id = %s AND view_id = %s AND revision = %s RETURNING *",
                [document, self._scope_id, self._experiment_id, view_id, expected_revision],
            )
        rows = _saved(cursor, await cursor.fetchall())
        if not rows:
            raise ComparisonRevisionConflict("The definition changed; reload before saving")
        return rows[0]


class ComparisonViewRepository:
    """Keep application writes separate from the existing evidence query adapters."""

    def __init__(self, database: ConsoleDatabase, scope_id: str) -> None:
        """Bind every definition operation to the configured process scope."""
        self._database = database
        self._scope_id = scope_id

    @asynccontextmanager
    async def session(self, experiment_id: str, *, write: bool = False) -> AsyncIterator[ComparisonViewSession]:
        """Roll back a failed command and translate concurrent writes explicitly."""
        transaction = self._database.command_transaction if write else self._database.transaction
        try:
            async with transaction() as connection:
                yield ComparisonViewSession(connection, self._scope_id, experiment_id)
        except ConsoleDatabaseUnavailable as exc:
            if isinstance(exc.__cause__, psycopg.errors.SerializationFailure):
                raise ComparisonRevisionConflict("Concurrent edit; reload before saving") from exc
            raise
