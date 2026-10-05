"""PostgreSQL adapter for public agent-session evidence and command intents."""

from __future__ import annotations

from collections.abc import AsyncIterator, Mapping
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from ..contracts import AgentSessionCommandRecord, AgentSessionCommandRequest
from .agent_sessions_schema import (
    CATALOG_SQL,
    COMMAND_COLUMNS,
    RECEIPT_COLUMNS,
    SESSION_COLUMNS,
    PUBLIC_STATE_COLUMNS,
    AgentSessionStorageUnavailable,
)
from .database import ConsoleDatabase, ConsoleDatabaseUnavailable
from .resources import _row_dicts


class AgentSessionNotFound(RuntimeError):
    """The requested agent session does not exist in the configured scope."""


class AgentSessionCommandConflict(RuntimeError):
    """An idempotency key is already bound to different command content."""


@dataclass(frozen=True)
class AgentSessionSource:
    """Normalized producer rows used to build the redacted Console projection."""

    session: Mapping[str, Any]
    receipts: tuple[Mapping[str, Any], ...]
    commands: tuple[AgentSessionCommandRecord, ...]
    public_state: Mapping[str, Any] | None = None


def _catalog(rows: list[Any]) -> dict[tuple[str, str], dict[str, str]]:
    """Normalize information-schema rows into relation column maps."""
    observed: dict[tuple[str, str], dict[str, str]] = {}
    for row in rows:
        if isinstance(row, Mapping):
            schema = str(row.get("table_schema") or "")
            table = str(row.get("table_name") or "")
            column = str(row.get("column_name") or "")
            udt = str(row.get("udt_name") or "")
        else:
            schema, table, column, udt = (str(value) for value in row)
        observed.setdefault((schema, table), {})[column] = udt
    return observed


def _stored_command(record: Mapping[str, Any]) -> AgentSessionCommandRecord:
    """Normalize one command row through the closed transport contract."""
    payload = {
        key: value
        for key, value in record.items()
        if key in AgentSessionCommandRecord.model_fields
    }
    payload["command_id"] = str(payload.get("command_id") or "")
    payload["session_id"] = str(payload.get("session_id") or "")
    payload["command"] = str(payload.get("command") or "")
    payload["requested_by"] = str(payload.get("requested_by") or "")
    payload["status"] = str(payload.get("status") or "")
    requested_at = payload.get("requested_at")
    if not isinstance(requested_at, datetime):
        payload["requested_at"] = datetime.now(timezone.utc)
    return AgentSessionCommandRecord.model_validate(payload)


class AgentSessionRepositorySession:
    """One transaction bound to one Console scope."""

    def __init__(self, connection: Any, scope_id: str) -> None:
        """Bind trusted scope identity to every command query."""
        self._connection = connection
        self._scope_id = scope_id

    async def require_storage(self) -> None:
        """Refuse absent producer projections or command storage."""
        cursor = await self._connection.execute(CATALOG_SQL)
        observed = _catalog(await cursor.fetchall())
        expected = {
            ("public", "research_agent_sessions"): SESSION_COLUMNS,
            ("public", "research_agent_decision_receipts"): RECEIPT_COLUMNS,
            ("console_app", "agent_session_commands"): COMMAND_COLUMNS,
            ("console_app", "agent_session_public_states"): PUBLIC_STATE_COLUMNS,
        }
        if observed != expected:
            raise AgentSessionStorageUnavailable(
                "Install the agent-session projection and command storage explicitly"
            )

    async def get(self, session_id: str) -> AgentSessionSource | None:
        """Read one immutable session and its public decision trajectory."""
        cursor = await self._connection.execute(
            "SELECT * FROM research_agent_sessions WHERE session_id = %s LIMIT 1",
            [session_id],
        )
        session_rows = _row_dicts(cursor, await cursor.fetchall())
        if not session_rows:
            return None
        receipt_cursor = await self._connection.execute(
            "SELECT * FROM research_agent_decision_receipts "
            "WHERE session_id = %s ORDER BY branch_id, sequence",
            [session_id],
        )
        receipt_rows = _row_dicts(receipt_cursor, await receipt_cursor.fetchall())
        command_cursor = await self._connection.execute(
            "SELECT * FROM console_app.agent_session_commands "
            "WHERE scope_id = %s AND session_id = %s ORDER BY requested_at, command_id",
            [self._scope_id, session_id],
        )
        command_rows = _row_dicts(command_cursor, await command_cursor.fetchall())
        state_cursor = await self._connection.execute(
            "SELECT * FROM console_app.agent_session_public_states "
            "WHERE scope_id = %s AND session_id = %s LIMIT 1",
            [self._scope_id, session_id],
        )
        state_rows = _row_dicts(state_cursor, await state_cursor.fetchall())
        return AgentSessionSource(
            session=session_rows[0],
            receipts=tuple(receipt_rows),
            commands=tuple(_stored_command(row) for row in command_rows),
            public_state=state_rows[0] if state_rows else None,
        )

    async def create_command(
        self,
        session_id: str,
        request: AgentSessionCommandRequest,
        *,
        requested_by: str,
        command_id: UUID | None = None,
    ) -> AgentSessionCommandRecord:
        """Append one human command intent or return its exact idempotent replay."""
        existing_cursor = await self._connection.execute(
            "SELECT * FROM console_app.agent_session_commands "
            "WHERE scope_id = %s AND idempotency_key = %s LIMIT 1",
            [self._scope_id, request.idempotency_key],
        )
        existing = _row_dicts(existing_cursor, await existing_cursor.fetchall())
        if existing:
            stored = _stored_command(existing[0])
            if (
                stored.session_id != session_id
                or stored.command != request.command
                or stored.reason != request.reason
                or stored.operator_answer != request.operator_answer
                or stored.approved != request.approved
                or stored.requested_by != requested_by
            ):
                raise AgentSessionCommandConflict(
                    "idempotency key is already bound to different command content"
                )
            return stored
        cursor = await self._connection.execute(
            "INSERT INTO console_app.agent_session_commands ("
            "scope_id, command_id, session_id, command, idempotency_key, requested_by, "
            "status, reason, operator_answer, approved"
            ") VALUES (%s, %s, %s, %s, %s, %s, 'requested', %s, %s, %s) RETURNING *",
            [
                self._scope_id,
                command_id or uuid4(),
                session_id,
                request.command,
                request.idempotency_key,
                requested_by,
                request.reason,
                request.operator_answer,
                request.approved,
            ],
        )
        rows = _row_dicts(cursor, await cursor.fetchall())
        if not rows:
            raise AgentSessionCommandConflict("agent session command could not be stored")
        return _stored_command(rows[0])

    async def get_command(self, command_id: UUID) -> AgentSessionCommandRecord | None:
        """Read one exact command receipt inside this Console scope."""
        cursor = await self._connection.execute(
            "SELECT * FROM console_app.agent_session_commands "
            "WHERE scope_id = %s AND command_id = %s LIMIT 1",
            [self._scope_id, command_id],
        )
        rows = _row_dicts(cursor, await cursor.fetchall())
        return _stored_command(rows[0]) if rows else None

    async def list_commands(
        self,
        session_id: str,
        limit: int,
        offset: int,
    ) -> tuple[list[AgentSessionCommandRecord], int]:
        """Return bounded command history for one session."""
        count_cursor = await self._connection.execute(
            "SELECT count(*) FROM console_app.agent_session_commands "
            "WHERE scope_id = %s AND session_id = %s",
            [self._scope_id, session_id],
        )
        total = int((await count_cursor.fetchone())[0])
        cursor = await self._connection.execute(
            "SELECT * FROM console_app.agent_session_commands "
            "WHERE scope_id = %s AND session_id = %s "
            "ORDER BY requested_at DESC, command_id DESC LIMIT %s OFFSET %s",
            [self._scope_id, session_id, limit, offset],
        )
        return [_stored_command(row) for row in _row_dicts(cursor, await cursor.fetchall())], total


class AgentSessionRepository:
    """Scope-bound repository with read and command transaction policies."""

    def __init__(self, database: ConsoleDatabase, scope_id: str) -> None:
        """Bind the repository to one server-owned Console scope."""
        self._database = database
        self.scope_id = scope_id

    @asynccontextmanager
    async def session(self, *, write: bool = False) -> AsyncIterator[AgentSessionRepositorySession]:
        """Yield one transaction and translate database failures consistently."""
        context = self._database.command_transaction() if write else self._database.transaction()
        async with context as connection:
            yield AgentSessionRepositorySession(connection, self.scope_id)


__all__ = [
    "AgentSessionCommandConflict",
    "AgentSessionNotFound",
    "AgentSessionRepository",
    "AgentSessionRepositorySession",
    "AgentSessionSource",
    "ConsoleDatabaseUnavailable",
]
