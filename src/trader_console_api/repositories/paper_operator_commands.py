"""Scoped persistence for authorized paper-runtime operator commands."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any
from uuid import UUID, uuid4

import psycopg
from pydantic import ValidationError

from ..contracts import PaperOperatorCommandRecord, PaperOperatorCommandRequest
from .database import ConsoleDatabase, ConsoleDatabaseUnavailable
from .paper_operator_commands_schema import (
    CATALOG_SQL,
    COLUMNS,
    PaperOperatorCommandStorageUnavailable,
)
from .resources import _row_dicts


class PaperOperatorCommandConflict(RuntimeError):
    """An idempotency key was reused for a different command request."""


class PaperOperatorCommandNotFound(RuntimeError):
    """The requested command is absent from the configured Console scope."""


def _stored(cursor: Any, rows: list[Any]) -> list[PaperOperatorCommandRecord]:
    """Normalize command rows into the closed public audit contract."""
    try:
        records = _row_dicts(cursor, rows)
        for record in records:
            record["command_id"] = str(record["command_id"])
        return [PaperOperatorCommandRecord.model_validate(record) for record in records]
    except (KeyError, TypeError, ValidationError) as exc:
        raise PaperOperatorCommandStorageUnavailable(
            "Stored paper operator command format is incompatible"
        ) from exc


class PaperOperatorCommandSession:
    """One command or query transaction bound to a server-owned scope."""

    def __init__(self, connection: Any, scope_id: str) -> None:
        """Bind trusted scope identity to every command SQL operation."""
        self._connection = connection
        self._scope_id = scope_id

    async def require_storage(self) -> None:
        """Refuse absent or incompatible storage without creating relations."""
        cursor = await self._connection.execute(CATALOG_SQL)
        if dict(await cursor.fetchall()) != COLUMNS:
            raise PaperOperatorCommandStorageUnavailable(
                "Install paper operator command storage explicitly"
            )

    async def admission(self, admission_id: str) -> dict[str, Any] | None:
        """Load the immutable research admission projection for validation."""
        cursor = await self._connection.execute(
            "SELECT admission_id, decision, status, expires_at, revoked_at, payload "
            "FROM research_paper_candidate_admissions WHERE admission_id = %s",
            [admission_id],
        )
        rows = await cursor.fetchall()
        if not rows:
            return None
        values = _row_dicts(cursor, rows)[0]
        return dict(values)

    async def submit(
        self,
        request: PaperOperatorCommandRequest,
        *,
        requested_by: str,
        request_digest: str,
    ) -> PaperOperatorCommandRecord:
        """Persist one request, returning an exact idempotent replay."""
        existing_cursor = await self._connection.execute(
            "SELECT command, admission_id, reason, requested_by, request_digest "
            "FROM paper_operator_commands "
            "WHERE scope_id = %s AND idempotency_key = %s",
            [self._scope_id, request.idempotency_key],
        )
        existing_identity = await existing_cursor.fetchall()
        if existing_identity:
            command, admission_id, reason, stored_requested_by, stored_digest = existing_identity[0]
            if (
                command != request.command
                or admission_id != request.admission_id
                or stored_requested_by != requested_by
                or stored_digest != request_digest
                or (reason or "") != (request.reason or "")
            ):
                raise PaperOperatorCommandConflict(
                    "Idempotency key is already bound to a different paper command"
                )
            cursor = await self._connection.execute(
                "SELECT * FROM paper_operator_commands "
                "WHERE scope_id = %s AND idempotency_key = %s",
                [self._scope_id, request.idempotency_key],
            )
            return _stored(cursor, await cursor.fetchall())[0]

        cursor = await self._connection.execute(
            "INSERT INTO paper_operator_commands "
            "(command_id, scope_id, command, admission_id, idempotency_key, request_digest, "
            "requested_by, reason, status) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'requested') "
            "ON CONFLICT (scope_id, idempotency_key) DO NOTHING RETURNING *",
            [
                uuid4(),
                self._scope_id,
                request.command,
                request.admission_id,
                request.idempotency_key,
                request_digest,
                requested_by,
                request.reason,
            ],
        )
        rows = _stored(cursor, await cursor.fetchall())
        if rows:
            return rows[0]
        cursor = await self._connection.execute(
            "SELECT * FROM paper_operator_commands "
            "WHERE scope_id = %s AND idempotency_key = %s",
            [self._scope_id, request.idempotency_key],
        )
        rows = _stored(cursor, await cursor.fetchall())
        if not rows:
            raise PaperOperatorCommandNotFound(
                "Paper operator command was not available after submit"
            )
        row = rows[0]
        if row.command != request.command or row.admission_id != request.admission_id or row.requested_by != requested_by:
            raise PaperOperatorCommandConflict(
                "Idempotency key is already bound to a different paper command"
            )
        return row

    async def get(self, command_id: UUID) -> PaperOperatorCommandRecord | None:
        """Load one command by identity inside the configured scope."""
        cursor = await self._connection.execute(
            "SELECT * FROM paper_operator_commands "
            "WHERE scope_id = %s AND command_id = %s",
            [self._scope_id, command_id],
        )
        rows = _stored(cursor, await cursor.fetchall())
        return rows[0] if rows else None

    async def list(self, limit: int, offset: int) -> tuple[list[PaperOperatorCommandRecord], int]:
        """Return bounded audit history in request order."""
        count_cursor = await self._connection.execute(
            "SELECT count(*) FROM paper_operator_commands WHERE scope_id = %s",
            [self._scope_id],
        )
        total = int((await count_cursor.fetchone())[0])
        cursor = await self._connection.execute(
            "SELECT * FROM paper_operator_commands WHERE scope_id = %s "
            "ORDER BY requested_at DESC, command_id DESC LIMIT %s OFFSET %s",
            [self._scope_id, limit, offset],
        )
        return _stored(cursor, await cursor.fetchall()), total


class PaperOperatorCommandRepository:
    """Keep operator command persistence separate from runtime execution."""

    def __init__(self, database: ConsoleDatabase, scope_id: str) -> None:
        """Bind every operation to the configured process scope."""
        self._database = database
        self._scope_id = scope_id

    @asynccontextmanager
    async def session(self, *, write: bool = False) -> AsyncIterator[PaperOperatorCommandSession]:
        """Yield one read or command transaction and translate database failures."""
        transaction = self._database.command_transaction if write else self._database.transaction
        try:
            async with transaction() as connection:
                yield PaperOperatorCommandSession(connection, self._scope_id)
        except ConsoleDatabaseUnavailable as exc:
            if isinstance(exc.__cause__, psycopg.errors.UniqueViolation):
                raise PaperOperatorCommandConflict(
                    "A paper operator command with this identity already exists"
                ) from exc
            raise


__all__ = [
    "PaperOperatorCommandConflict",
    "PaperOperatorCommandNotFound",
    "PaperOperatorCommandRepository",
    "PaperOperatorCommandSession",
    "PaperOperatorCommandStorageUnavailable",
]
