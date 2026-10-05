"""Explicit storage contract for Console agent-session reads and commands."""

from __future__ import annotations

from argparse import ArgumentParser
from collections.abc import Mapping, Sequence
import os
from typing import Any

import psycopg


SESSION_COLUMNS = {
    "session_id": "text",
    "operator_id": "text",
    "model_profile_id": "text",
    "tool_catalog_id": "text",
    "status": "text",
    "payload": "jsonb",
}

RECEIPT_COLUMNS = {
    "receipt_id": "text",
    "session_id": "text",
    "branch_id": "text",
    "sequence": "int4",
    "actor": "text",
    "program_id": "text",
    "model_profile_id": "text",
    "action": "text",
    "status": "text",
    "decision_digest": "text",
    "evidence_ref_count": "int4",
    "payload": "jsonb",
}

COMMAND_COLUMNS = {
    "scope_id": "text",
    "command_id": "uuid",
    "session_id": "text",
    "command": "text",
    "idempotency_key": "text",
    "requested_by": "text",
    "status": "text",
    "reason": "text",
    "operator_answer": "text",
    "approved": "bool",
    "outcome_code": "text",
    "outcome_message": "text",
    "worker_id": "text",
    "attempt": "int4",
    "started_at": "timestamptz",
    "heartbeat_at": "timestamptz",
    "lease_expires_at": "timestamptz",
    "requested_at": "timestamptz",
    "completed_at": "timestamptz",
}

PUBLIC_STATE_COLUMNS = {
    "scope_id": "text",
    "session_id": "text",
    "session_digest": "text",
    "operator_id": "text",
    "checkpoint_sequence": "int4",
    "public_state": "jsonb",
    "updated_at": "timestamptz",
}

CATALOG_SQL = """
SELECT table_schema, table_name, column_name, udt_name
FROM information_schema.columns
WHERE (table_schema = 'public' AND table_name IN (
    'research_agent_sessions', 'research_agent_decision_receipts'
)) OR (table_schema = 'console_app' AND table_name = 'agent_session_commands')
OR (table_schema = 'console_app' AND table_name = 'agent_session_public_states')
ORDER BY table_schema, table_name, ordinal_position
"""

INSTALL_SQL = """
CREATE SCHEMA IF NOT EXISTS console_app;
CREATE TABLE IF NOT EXISTS console_app.agent_session_commands (
    scope_id TEXT NOT NULL,
    command_id UUID PRIMARY KEY,
    session_id TEXT NOT NULL,
    command TEXT NOT NULL CHECK (command IN ('inspect', 'interrupt', 'resume', 'cancel')),
    idempotency_key TEXT NOT NULL,
    requested_by TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('requested', 'accepted', 'completed', 'rejected', 'ambiguous')),
    reason TEXT,
    operator_answer TEXT,
    approved BOOLEAN,
    outcome_code TEXT,
    outcome_message TEXT,
    worker_id TEXT,
    attempt INTEGER NOT NULL DEFAULT 0 CHECK (attempt >= 0),
    started_at TIMESTAMPTZ,
    heartbeat_at TIMESTAMPTZ,
    lease_expires_at TIMESTAMPTZ,
    requested_at TIMESTAMPTZ NOT NULL DEFAULT transaction_timestamp(),
    completed_at TIMESTAMPTZ,
    UNIQUE (scope_id, idempotency_key)
);
CREATE TABLE IF NOT EXISTS console_app.agent_session_public_states (
    scope_id TEXT NOT NULL,
    session_id TEXT NOT NULL,
    session_digest TEXT NOT NULL CHECK (session_digest ~ '^[0-9a-f]{64}$'),
    operator_id TEXT NOT NULL,
    checkpoint_sequence INTEGER CHECK (checkpoint_sequence IS NULL OR checkpoint_sequence >= 1),
    public_state JSONB NOT NULL CHECK (jsonb_typeof(public_state) = 'object'),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT transaction_timestamp(),
    PRIMARY KEY (scope_id, session_id)
);
"""


class AgentSessionStorageUnavailable(RuntimeError):
    """Agent session evidence or command storage is absent/incompatible."""


def install_agent_session_schema(connection: psycopg.Connection) -> None:
    """Install only the additive Console command-intent table.

    The producer-owned ``research_agent_*`` relations are installed by the
    research artifact store and are never created or altered here.
    """
    connection.execute(INSTALL_SQL)
    rows = connection.execute(CATALOG_SQL).fetchall()
    observed = _catalog(rows)
    expected = {
        ("public", "research_agent_sessions"): SESSION_COLUMNS,
        ("public", "research_agent_decision_receipts"): RECEIPT_COLUMNS,
        ("console_app", "agent_session_commands"): COMMAND_COLUMNS,
        ("console_app", "agent_session_public_states"): PUBLIC_STATE_COLUMNS,
    }
    if observed != expected:
        raise AgentSessionStorageUnavailable(
            "Agent session storage has an incompatible column shape"
        )


def _catalog(rows: Sequence[Any]) -> dict[tuple[str, str], dict[str, str]]:
    """Normalize information-schema rows for the explicit installer."""
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


def main(arguments: list[str] | None = None) -> None:
    """Install or inspect agent-session storage using the explicit API DSN."""
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("install", "status"))
    options = parser.parse_args(arguments)
    dsn = os.environ.get("TRADER_CONSOLE_DATABASE_URL")
    if not dsn:
        parser.error("Set TRADER_CONSOLE_DATABASE_URL explicitly")
    try:
        with psycopg.connect(dsn, connect_timeout=5) as connection:
            connection.execute("SET LOCAL statement_timeout = '10s'")
            connection.execute("SET LOCAL lock_timeout = '3s'")
            if options.action == "install":
                install_agent_session_schema(connection)
            else:
                observed = _catalog(connection.execute(CATALOG_SQL).fetchall())
                expected = {
                    ("public", "research_agent_sessions"): SESSION_COLUMNS,
                    ("public", "research_agent_decision_receipts"): RECEIPT_COLUMNS,
                    ("console_app", "agent_session_commands"): COMMAND_COLUMNS,
                    ("console_app", "agent_session_public_states"): PUBLIC_STATE_COLUMNS,
                }
                if observed != expected:
                    raise AgentSessionStorageUnavailable(
                        "Agent session storage is missing or incompatible"
                    )
    except (psycopg.Error, AgentSessionStorageUnavailable) as exc:
        parser.exit(
            1,
            f"Agent session storage {options.action} failed ({type(exc).__name__}).\n",
        )
    print("Agent session storage version 1 is available.")


__all__ = [
    "CATALOG_SQL",
    "COMMAND_COLUMNS",
    "INSTALL_SQL",
    "PUBLIC_STATE_COLUMNS",
    "RECEIPT_COLUMNS",
    "SESSION_COLUMNS",
    "AgentSessionStorageUnavailable",
    "install_agent_session_schema",
]


if __name__ == "__main__":
    main()
