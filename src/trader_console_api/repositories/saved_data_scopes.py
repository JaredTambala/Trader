"""Persistence adapter for immutable Console saved data scopes."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any
from uuid import UUID, uuid4

import psycopg
from psycopg.types.json import Jsonb
from pydantic import ValidationError

from ..data_scope_contracts import (
    DataScopeEvidenceStatus,
    SavedDataScope,
    SavedDataScopeCreate,
)
from .database import ConsoleDatabase, ConsoleDatabaseUnavailable
from .resources import _row_dicts
from .saved_data_scopes_schema import (
    CATALOG_SQL,
    COLUMNS,
    SavedDataScopeStorageUnavailable,
)


class SavedDataScopeNotFound(RuntimeError):
    """The requested saved scope is absent from the configured Console scope."""


class SavedDataScopeConflict(RuntimeError):
    """A saved-scope fingerprint or idempotency key conflicts with existing data."""


class SavedDataScopeEvidenceUnavailable(RuntimeError):
    """The producer evidence projection cannot qualify a saved scope."""


def _stored(cursor: Any, rows: list[Any]) -> list[SavedDataScope]:
    """Normalize database rows into the closed saved-scope contract."""
    try:
        records = _row_dicts(cursor, rows)
        values: list[SavedDataScope] = []
        for record in records:
            payload = dict(record.get("scope") or {})
            payload.update(
                {
                    "saved_scope_id": str(record["saved_scope_id"]),
                    "scope_id": record["scope_id"],
                    "revision": record["revision"],
                    "fingerprint": record["fingerprint"],
                    "evidence_status": record["evidence_status"],
                    "evidence_reason": record.get("evidence_reason"),
                    "created_by": record["created_by"],
                    "idempotency_key": record["idempotency_key"],
                    "created_at": record["created_at"],
                    "updated_at": record["updated_at"],
                }
            )
            values.append(SavedDataScope.model_validate(payload))
        return values
    except (KeyError, TypeError, ValidationError) as exc:
        raise SavedDataScopeStorageUnavailable(
            "Stored saved data scope format is incompatible"
        ) from exc


def _scope_payload(scope: SavedDataScopeCreate) -> dict[str, Any]:
    """Build the immutable scope document stored beside generated identity fields."""
    return scope.model_dump(
        mode="json",
        exclude={"evidence_status", "evidence_reason", "idempotency_key"},
    )


class SavedDataScopeSession:
    """One transaction bound to a server-owned Console scope."""

    def __init__(self, connection: Any, scope_id: str) -> None:
        """Bind trusted scope identity to every SQL operation."""
        self._connection = connection
        self._scope_id = scope_id

    async def require_storage(self) -> None:
        """Refuse absent or incompatible storage without creating relations."""
        cursor = await self._connection.execute(CATALOG_SQL)
        if dict(await cursor.fetchall()) != COLUMNS:
            raise SavedDataScopeStorageUnavailable(
                "Install Console saved data scope storage explicitly"
            )

    async def create(
        self,
        request: SavedDataScopeCreate,
        *,
        fingerprint: str,
        saved_scope_id: UUID | None = None,
    ) -> SavedDataScope:
        """Persist one exact scope, returning an exact idempotent replay."""
        existing_cursor = await self._connection.execute(
            "SELECT * FROM console_app.saved_data_scopes "
            "WHERE scope_id = %s AND (idempotency_key = %s OR fingerprint = %s) "
            "LIMIT 1",
            [self._scope_id, request.idempotency_key, fingerprint],
        )
        existing = _stored(existing_cursor, await existing_cursor.fetchall())
        if existing:
            if existing[0].fingerprint != fingerprint:
                raise SavedDataScopeConflict(
                    "Idempotency key is already bound to a different data scope"
                )
            return existing[0]
        cursor = await self._connection.execute(
            "INSERT INTO console_app.saved_data_scopes "
            "(scope_id, saved_scope_id, revision, fingerprint, idempotency_key, scope, "
            "created_by, evidence_status, evidence_reason) "
            "VALUES (%s, %s, 1, %s, %s, %s, %s, %s, %s) RETURNING *",
            [
                self._scope_id,
                saved_scope_id or uuid4(),
                fingerprint,
                request.idempotency_key,
                Jsonb(_scope_payload(request)),
                request.created_by,
                request.evidence_status.value,
                request.evidence_reason,
            ],
        )
        rows = _stored(cursor, await cursor.fetchall())
        if not rows:
            raise SavedDataScopeConflict("Saved data scope could not be stored")
        return rows[0]

    async def get(self, saved_scope_id: UUID) -> SavedDataScope | None:
        """Load one immutable scope identity from the configured process scope."""
        cursor = await self._connection.execute(
            "SELECT * FROM console_app.saved_data_scopes "
            "WHERE scope_id = %s AND saved_scope_id = %s",
            [self._scope_id, saved_scope_id],
        )
        rows = _stored(cursor, await cursor.fetchall())
        return rows[0] if rows else None

    async def list(self, limit: int, offset: int) -> tuple[list[SavedDataScope], int]:
        """Return saved scopes in stable update order with bounded pagination."""
        count_cursor = await self._connection.execute(
            "SELECT count(*) FROM console_app.saved_data_scopes WHERE scope_id = %s",
            [self._scope_id],
        )
        total = int((await count_cursor.fetchone())[0])
        cursor = await self._connection.execute(
            "SELECT * FROM console_app.saved_data_scopes WHERE scope_id = %s "
            "ORDER BY updated_at DESC, saved_scope_id LIMIT %s OFFSET %s",
            [self._scope_id, limit, offset],
        )
        return _stored(cursor, await cursor.fetchall()), total

    async def current_evidence(self, scope: SavedDataScope) -> tuple[DataScopeEvidenceStatus, str | None] | None:
        """Read exact producer evidence without recreating Data quality calculations.

        The projection is optional while the Data/Console contract is being rolled out. A
        missing projection or row is represented by ``None`` and is handled as unavailable
        by the application service.
        """
        cursor = await self._connection.execute(
            "SELECT evidence_status, evidence_reason, manifest_artifact_id, quality_artifact_id "
            "FROM console_read.data_scope_evidence "
            "WHERE manifest_artifact_id = %s AND quality_artifact_id = %s "
            "AND asset_class = %s AND timeframe = %s AND interval = %s "
            "AND requested_start = %s AND requested_end = %s",
            [
                scope.manifest_artifact_id,
                scope.quality_artifact_id,
                scope.asset_class,
                scope.timeframe,
                scope.interval,
                scope.start,
                scope.end,
            ],
        )
        rows = await cursor.fetchall()
        if not rows:
            return None
        values = _row_dicts(cursor, rows)[0]
        if (
            values.get("manifest_artifact_id") != scope.manifest_artifact_id
            or values.get("quality_artifact_id") != scope.quality_artifact_id
        ):
            return None
        return DataScopeEvidenceStatus(str(values.get("evidence_status"))), values.get("evidence_reason")

    async def update_evidence(
        self,
        saved_scope_id: UUID,
        *,
        status: DataScopeEvidenceStatus,
        reason: str | None,
    ) -> SavedDataScope | None:
        """Update only mutable qualification state while preserving scope identity."""
        cursor = await self._connection.execute(
            "UPDATE console_app.saved_data_scopes SET evidence_status = %s, "
            "evidence_reason = %s, updated_at = transaction_timestamp() "
            "WHERE scope_id = %s AND saved_scope_id = %s RETURNING *",
            [status.value, reason, self._scope_id, saved_scope_id],
        )
        rows = _stored(cursor, await cursor.fetchall())
        return rows[0] if rows else None


class SavedDataScopeRepository:
    """Keep saved-scope persistence separate from producer evidence adapters."""

    def __init__(self, database: ConsoleDatabase, scope_id: str) -> None:
        """Bind every operation to the configured process scope."""
        self._database = database
        self._scope_id = scope_id

    @asynccontextmanager
    async def session(self, *, write: bool = False) -> AsyncIterator[SavedDataScopeSession]:
        """Yield one read or command transaction and translate database failures."""
        transaction = self._database.command_transaction if write else self._database.transaction
        try:
            async with transaction() as connection:
                yield SavedDataScopeSession(connection, self._scope_id)
        except ConsoleDatabaseUnavailable as exc:
            if isinstance(exc.__cause__, psycopg.errors.UniqueViolation):
                raise SavedDataScopeConflict(
                    "A saved data scope with this identity already exists"
                ) from exc
            raise


__all__ = [
    "SavedDataScopeConflict",
    "SavedDataScopeEvidenceUnavailable",
    "SavedDataScopeNotFound",
    "SavedDataScopeRepository",
    "SavedDataScopeSession",
    "SavedDataScopeStorageUnavailable",
]
