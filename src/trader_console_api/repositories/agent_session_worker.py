"""Durable claim and evidence writes for the agent-session command worker.

The API records human command intents. This repository owns the separate worker
lease and the Console-owned public-state snapshot. It reads producer session
rows but never writes producer evidence or runtime checkpoints.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Mapping
from contextlib import asynccontextmanager
from typing import Any
from uuid import UUID

from trader_research.governance import ResearchSession

from ..contracts import AgentSessionCommandRecord
from .database import ConsoleDatabase
from .resources import _row_dicts


def _stored(record: Mapping[str, Any]) -> AgentSessionCommandRecord:
    """Normalize one worker command row into the public receipt contract."""
    payload = {
        key: record.get(key)
        for key in AgentSessionCommandRecord.model_fields
        if key in record
    }
    payload["command_id"] = str(payload.get("command_id") or "")
    payload["session_id"] = str(payload.get("session_id") or "")
    return AgentSessionCommandRecord.model_validate(payload)


class AgentSessionWorkerSession:
    """One write transaction bound to one Console scope."""

    def __init__(self, connection: Any, scope_id: str) -> None:
        """Bind worker SQL to the server-owned scope."""
        self._connection = connection
        self._scope_id = scope_id

    async def claim_next(
        self,
        *,
        worker_id: str,
        lease_seconds: int,
        max_attempts: int,
    ) -> AgentSessionCommandRecord | None:
        """Claim one command; expired accepted work is always ambiguous."""
        await self._connection.execute(
            "UPDATE console_app.agent_session_commands "
            "SET status = 'ambiguous', outcome_code = 'worker_lease_expired', "
            "outcome_message = 'A worker lease expired before the command outcome was durable', "
            "worker_id = NULL, heartbeat_at = NULL, lease_expires_at = NULL, "
            "completed_at = transaction_timestamp() "
            "WHERE scope_id = %s AND status = 'accepted' "
            "AND lease_expires_at < transaction_timestamp()",
            [self._scope_id],
        )
        cursor = await self._connection.execute(
            "WITH candidate AS ("
            "SELECT command_id FROM console_app.agent_session_commands "
            "WHERE scope_id = %s AND status = 'requested' AND attempt < %s "
            "ORDER BY requested_at, command_id LIMIT 1 FOR UPDATE SKIP LOCKED"
            ") UPDATE console_app.agent_session_commands AS command "
            "SET status = 'accepted', worker_id = %s, attempt = command.attempt + 1, "
            "started_at = COALESCE(command.started_at, transaction_timestamp()), "
            "heartbeat_at = transaction_timestamp(), "
            "lease_expires_at = transaction_timestamp() + (%s * interval '1 second') "
            "FROM candidate WHERE command.scope_id = %s "
            "AND command.command_id = candidate.command_id RETURNING command.*",
            [self._scope_id, max_attempts, worker_id, lease_seconds, self._scope_id],
        )
        rows = _row_dicts(cursor, await cursor.fetchall())
        return _stored(rows[0]) if rows else None

    async def load_session(self, session_id: str) -> ResearchSession | None:
        """Load and verify one immutable producer-owned session artifact."""
        cursor = await self._connection.execute(
            "SELECT operator_id, payload FROM research_agent_sessions "
            "WHERE session_id = %s LIMIT 1",
            [session_id],
        )
        rows = _row_dicts(cursor, await cursor.fetchall())
        if not rows:
            return None
        row = rows[0]
        payload = row.get("payload")
        if not isinstance(payload, Mapping):
            raise ValueError("research session payload is unavailable")
        session = ResearchSession.from_dict(payload)
        if str(row.get("operator_id") or "") != session.operator_id:
            raise ValueError("research session owner projection is inconsistent")
        return session

    async def heartbeat(
        self,
        command_id: UUID,
        *,
        worker_id: str,
        lease_seconds: int,
    ) -> bool:
        """Extend one command lease only while this worker still owns it."""
        cursor = await self._connection.execute(
            "UPDATE console_app.agent_session_commands SET heartbeat_at = transaction_timestamp(), "
            "lease_expires_at = transaction_timestamp() + (%s * interval '1 second') "
            "WHERE scope_id = %s AND command_id = %s AND status = 'accepted' AND worker_id = %s "
            "RETURNING command_id",
            [lease_seconds, self._scope_id, command_id, worker_id],
        )
        return bool(await cursor.fetchall())

    async def finish(
        self,
        command_id: UUID,
        *,
        worker_id: str,
        status: str,
        outcome_code: str | None,
        outcome_message: str | None,
    ) -> bool:
        """Persist one terminal worker receipt while retaining lease ownership."""
        if status not in {"completed", "rejected", "ambiguous"}:
            raise ValueError("agent command finish status is not terminal")
        cursor = await self._connection.execute(
            "UPDATE console_app.agent_session_commands SET status = %s, outcome_code = %s, "
            "outcome_message = %s, completed_at = transaction_timestamp(), "
            "heartbeat_at = transaction_timestamp(), lease_expires_at = NULL "
            "WHERE scope_id = %s AND command_id = %s AND status = 'accepted' AND worker_id = %s "
            "RETURNING command_id",
            [
                status,
                outcome_code,
                outcome_message,
                self._scope_id,
                command_id,
                worker_id,
            ],
        )
        return bool(await cursor.fetchall())

    async def upsert_public_state(
        self,
        session: ResearchSession,
        public_state: Mapping[str, Any],
        *,
        checkpoint_sequence: int | None,
    ) -> None:
        """Persist the latest closed public projection without stale overwrite."""
        import psycopg.types.json

        await self._connection.execute(
            "INSERT INTO console_app.agent_session_public_states ("
            "scope_id, session_id, session_digest, operator_id, checkpoint_sequence, public_state"
            ") VALUES (%s, %s, %s, %s, %s, %s) "
            "ON CONFLICT (scope_id, session_id) DO UPDATE SET "
            "session_digest = EXCLUDED.session_digest, operator_id = EXCLUDED.operator_id, "
            "checkpoint_sequence = EXCLUDED.checkpoint_sequence, public_state = EXCLUDED.public_state, "
            "updated_at = transaction_timestamp() "
            "WHERE console_app.agent_session_public_states.checkpoint_sequence IS NULL "
            "OR EXCLUDED.checkpoint_sequence IS NULL "
            "OR EXCLUDED.checkpoint_sequence >= console_app.agent_session_public_states.checkpoint_sequence",
            [
                self._scope_id,
                session.session_id,
                session.session_digest,
                session.operator_id,
                checkpoint_sequence,
                psycopg.types.json.Jsonb(dict(public_state)),
            ],
        )


class AgentSessionWorkerRepository:
    """Scope-bound database access for the command worker."""

    def __init__(self, database: ConsoleDatabase, scope_id: str) -> None:
        """Bind worker operations to one configured scope."""
        self._database = database
        self._scope_id = scope_id

    @asynccontextmanager
    async def session(self) -> AsyncIterator[AgentSessionWorkerSession]:
        """Yield a write transaction for one claim or completion operation."""
        async with self._database.command_transaction() as connection:
            yield AgentSessionWorkerSession(connection, self._scope_id)


__all__ = ["AgentSessionWorkerRepository", "AgentSessionWorkerSession"]
