"""Scoped persistence for immutable Console backtest definition revisions."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any
from uuid import UUID, uuid4

import psycopg
from psycopg.types.json import Jsonb
from pydantic import ValidationError

from ..contracts import BacktestDefinition, BacktestDefinitionRevision
from .backtest_definitions_schema import (
    CATALOG_SQL,
    COLUMNS,
    BacktestDefinitionStorageUnavailable,
)
from .database import ConsoleDatabase, ConsoleDatabaseUnavailable
from .resources import _row_dicts


class BacktestDefinitionNotFound(RuntimeError):
    """The requested definition is absent from the configured scope."""


class BacktestDefinitionConflict(RuntimeError):
    """A fingerprint or concurrent definition revision conflicts with a write."""


def _stored(cursor: Any, rows: list[Any]) -> list[BacktestDefinitionRevision]:
    try:
        records = _row_dicts(cursor, rows)
        for record in records:
            record["definition_id"] = str(record["definition_id"])
        return [BacktestDefinitionRevision.model_validate(row) for row in records]
    except ValidationError as exc:
        raise BacktestDefinitionStorageUnavailable(
            "Stored backtest definition format is incompatible"
        ) from exc


class BacktestDefinitionSession:
    """One transaction bound to a server-owned scope."""

    def __init__(self, connection: Any, scope_id: str) -> None:
        """Bind trusted scope identity to every SQL operation."""
        self._connection = connection
        self._scope_id = scope_id

    async def require_storage(self) -> None:
        """Refuse absent or incompatible storage without creating relations."""
        cursor = await self._connection.execute(CATALOG_SQL)
        if dict(await cursor.fetchall()) != COLUMNS:
            raise BacktestDefinitionStorageUnavailable(
                "Install Console backtest definition storage explicitly"
            )

    async def create(
        self,
        definition: BacktestDefinition,
        *,
        fingerprint: str,
        definition_id: UUID | None = None,
    ) -> BacktestDefinitionRevision:
        """Insert the first immutable revision for one server-generated identity."""
        cursor = await self._connection.execute(
            "INSERT INTO console_app.backtest_definitions "
            "(scope_id, definition_id, definition_version, revision, fingerprint, definition) "
            "VALUES (%s, %s, 1, 1, %s, %s) RETURNING *",
            [
                self._scope_id,
                definition_id or uuid4(),
                fingerprint,
                Jsonb(definition.model_dump(mode="json")),
            ],
        )
        rows = _stored(cursor, await cursor.fetchall())
        if not rows:
            raise BacktestDefinitionConflict("Definition could not be stored")
        return rows[0]

    async def get(
        self,
        definition_id: UUID,
        *,
        revision: int | None = None,
    ) -> BacktestDefinitionRevision | None:
        """Load one revision, or the latest revision when unspecified."""
        if revision is None:
            query = (
                "SELECT * FROM console_app.backtest_definitions "
                "WHERE scope_id = %s AND definition_id = %s "
                "ORDER BY revision DESC LIMIT 1"
            )
            parameters: list[Any] = [self._scope_id, definition_id]
        else:
            query = (
                "SELECT * FROM console_app.backtest_definitions "
                "WHERE scope_id = %s AND definition_id = %s AND revision = %s"
            )
            parameters = [self._scope_id, definition_id, revision]
        cursor = await self._connection.execute(query, parameters)
        rows = _stored(cursor, await cursor.fetchall())
        return rows[0] if rows else None

    async def list(self, limit: int, offset: int) -> tuple[list[BacktestDefinitionRevision], int]:
        """Return the latest revision for each definition with bounded pagination."""
        cursor = await self._connection.execute(
            "SELECT count(DISTINCT definition_id) FROM console_app.backtest_definitions "
            "WHERE scope_id = %s",
            [self._scope_id],
        )
        total = int((await cursor.fetchone())[0])
        cursor = await self._connection.execute(
            "SELECT latest.* FROM ("
            "SELECT DISTINCT ON (definition_id) * FROM console_app.backtest_definitions "
            "WHERE scope_id = %s ORDER BY definition_id, revision DESC"
            ") AS latest ORDER BY updated_at DESC, definition_id LIMIT %s OFFSET %s",
            [self._scope_id, limit, offset],
        )
        return _stored(cursor, await cursor.fetchall()), total

    async def create_revision(
        self,
        definition_id: UUID,
        definition: BacktestDefinition,
        *,
        fingerprint: str,
    ) -> BacktestDefinitionRevision:
        """Append one immutable revision after requiring an existing identity."""
        latest = await self.get(definition_id)
        if latest is None:
            raise BacktestDefinitionNotFound("Backtest definition not found")
        cursor = await self._connection.execute(
            "INSERT INTO console_app.backtest_definitions "
            "(scope_id, definition_id, definition_version, revision, fingerprint, definition) "
            "VALUES (%s, %s, 1, %s, %s, %s) RETURNING *",
            [
                self._scope_id,
                definition_id,
                latest.revision + 1,
                fingerprint,
                Jsonb(definition.model_dump(mode="json")),
            ],
        )
        rows = _stored(cursor, await cursor.fetchall())
        if not rows:
            raise BacktestDefinitionConflict("Definition revision could not be stored")
        return rows[0]


class BacktestDefinitionRepository:
    """Keep Console definition writes separate from producer evidence adapters."""

    def __init__(self, database: ConsoleDatabase, scope_id: str) -> None:
        """Bind every operation to the configured process scope."""
        self._database = database
        self._scope_id = scope_id

    @asynccontextmanager
    async def session(self, *, write: bool = False) -> AsyncIterator[BacktestDefinitionSession]:
        """Yield one read or command transaction and translate database failures."""
        transaction = self._database.command_transaction if write else self._database.transaction
        try:
            async with transaction() as connection:
                yield BacktestDefinitionSession(connection, self._scope_id)
        except ConsoleDatabaseUnavailable as exc:
            if isinstance(exc.__cause__, psycopg.errors.UniqueViolation):
                raise BacktestDefinitionConflict(
                    "A definition with this fingerprint already exists in this scope"
                ) from exc
            raise


__all__ = [
    "BacktestDefinitionConflict",
    "BacktestDefinitionNotFound",
    "BacktestDefinitionRepository",
    "BacktestDefinitionSession",
]
