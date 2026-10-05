"""Explicit installer for the paper-runtime operator command ledger."""

from __future__ import annotations

from argparse import ArgumentParser
import os

import psycopg


COLUMNS = {
    "command_id": "uuid",
    "scope_id": "text",
    "command": "text",
    "admission_id": "text",
    "idempotency_key": "text",
    "request_digest": "text",
    "requested_by": "text",
    "reason": "text",
    "status": "text",
    "outcome_code": "text",
    "outcome_message": "text",
    "requested_at": "timestamptz",
    "accepted_at": "timestamptz",
    "completed_at": "timestamptz",
}

CATALOG_SQL = """
SELECT column_name, udt_name FROM information_schema.columns
WHERE table_schema = 'public' AND table_name = 'paper_operator_commands'
"""

INSTALL_SQL = """
CREATE TABLE IF NOT EXISTS paper_operator_commands (
    command_id uuid PRIMARY KEY,
    scope_id text NOT NULL CHECK (length(scope_id) BETWEEN 1 AND 100),
    command text NOT NULL CHECK (command IN ('start', 'pause', 'stop', 'set_halt', 'clear_halt', 'reconcile')),
    admission_id text NOT NULL CHECK (length(admission_id) BETWEEN 1 AND 200),
    idempotency_key text NOT NULL CHECK (length(idempotency_key) BETWEEN 1 AND 200),
    request_digest text NOT NULL CHECK (request_digest ~ '^[0-9a-f]{64}$'),
    requested_by text NOT NULL CHECK (length(requested_by) BETWEEN 1 AND 200),
    reason text,
    status text NOT NULL CHECK (status IN ('requested', 'accepted', 'completed', 'rejected', 'ambiguous', 'failed')),
    outcome_code text,
    outcome_message text,
    requested_at timestamptz NOT NULL DEFAULT transaction_timestamp(),
    accepted_at timestamptz,
    completed_at timestamptz,
    UNIQUE (scope_id, idempotency_key)
)
"""


class PaperOperatorCommandStorageUnavailable(RuntimeError):
    """Command storage is absent or has an incompatible column shape."""


def install_paper_operator_command_schema(connection: psycopg.Connection) -> None:
    """Install the additive command ledger in the caller's transaction."""
    connection.execute(INSTALL_SQL)
    if dict(connection.execute(CATALOG_SQL).fetchall()) != COLUMNS:
        raise PaperOperatorCommandStorageUnavailable(
            "Paper operator command storage has an incompatible column shape"
        )


def main(arguments: list[str] | None = None) -> None:
    """Install or inspect command storage using the explicit API DSN."""
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("install", "status"))
    options = parser.parse_args(arguments)
    dsn = os.environ.get("TRADER_CONSOLE_DATABASE_URL")
    if not dsn:
        parser.error("Set TRADER_CONSOLE_DATABASE_URL explicitly")
    try:
        with psycopg.connect(dsn, connect_timeout=5) as connection:
            if options.action == "status":
                connection.execute("SET TRANSACTION READ ONLY")
            connection.execute("SET LOCAL statement_timeout = '10s'")
            connection.execute("SET LOCAL lock_timeout = '3s'")
            if options.action == "install":
                install_paper_operator_command_schema(connection)
            elif dict(connection.execute(CATALOG_SQL).fetchall()) != COLUMNS:
                raise PaperOperatorCommandStorageUnavailable(
                    "Paper operator command storage is missing or incompatible"
                )
    except (psycopg.Error, PaperOperatorCommandStorageUnavailable) as exc:
        parser.exit(
            1,
            f"Paper operator command storage {options.action} failed ({type(exc).__name__}).\n",
        )
    print("Paper operator command storage version 1 is available.")


if __name__ == "__main__":
    main()


__all__ = [
    "COLUMNS",
    "CATALOG_SQL",
    "INSTALL_SQL",
    "PaperOperatorCommandStorageUnavailable",
    "install_paper_operator_command_schema",
]
