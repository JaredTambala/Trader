"""Explicit installer for durable Console backtest execution commands."""

from __future__ import annotations

from argparse import ArgumentParser
import os

import psycopg


COLUMNS = {
    "scope_id": "text",
    "execution_id": "uuid",
    "definition_id": "uuid",
    "definition_revision": "int4",
    "definition_fingerprint": "text",
    "idempotency_key": "text",
    "status": "text",
    "attempt": "int4",
    "worker_id": "text",
    "run_id": "text",
    "processed_cycles": "int4",
    "total_cycles": "int4",
    "last_decision_at": "timestamptz",
    "heartbeat_at": "timestamptz",
    "lease_expires_at": "timestamptz",
    "created_at": "timestamptz",
    "started_at": "timestamptz",
    "finished_at": "timestamptz",
    "warning_summary": "jsonb",
    "terminal_error_code": "text",
    "terminal_error_message": "text",
}
CATALOG_SQL = """
SELECT column_name, udt_name FROM information_schema.columns
WHERE table_schema = 'console_app' AND table_name = 'backtest_executions'
"""
INSTALL_SQL = """
CREATE TABLE IF NOT EXISTS console_app.backtest_executions (
    scope_id text NOT NULL,
    execution_id uuid NOT NULL,
    definition_id uuid NOT NULL,
    definition_revision integer NOT NULL CHECK (definition_revision >= 1),
    definition_fingerprint text NOT NULL CHECK (definition_fingerprint ~ '^[0-9a-f]{64}$'),
    idempotency_key text NOT NULL CHECK (length(idempotency_key) BETWEEN 1 AND 200),
    status text NOT NULL CHECK (status IN ('queued', 'running', 'completed', 'partial', 'failed', 'reconciliation_required')),
    attempt integer NOT NULL DEFAULT 0 CHECK (attempt >= 0),
    worker_id text,
    run_id text,
    processed_cycles integer NOT NULL DEFAULT 0 CHECK (processed_cycles >= 0),
    total_cycles integer CHECK (total_cycles IS NULL OR total_cycles >= 0),
    last_decision_at timestamptz,
    heartbeat_at timestamptz,
    lease_expires_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT transaction_timestamp(),
    started_at timestamptz,
    finished_at timestamptz,
    warning_summary jsonb NOT NULL DEFAULT '[]'::jsonb CHECK (jsonb_typeof(warning_summary) = 'array'),
    terminal_error_code text,
    terminal_error_message text,
    PRIMARY KEY (scope_id, execution_id),
    UNIQUE (scope_id, idempotency_key),
    FOREIGN KEY (scope_id, definition_id, definition_revision)
        REFERENCES console_app.backtest_definitions (scope_id, definition_id, revision)
)
"""


class BacktestExecutionStorageUnavailable(RuntimeError):
    """Execution storage is absent or incompatible; install it explicitly."""


def install_backtest_execution_schema(connection: psycopg.Connection) -> None:
    """Install only the additive execution table in the caller's transaction."""
    connection.execute("CREATE SCHEMA IF NOT EXISTS console_app")
    connection.execute(INSTALL_SQL)
    if dict(connection.execute(CATALOG_SQL).fetchall()) != COLUMNS:
        raise BacktestExecutionStorageUnavailable(
            "Backtest execution storage has an incompatible column shape"
        )


def main(arguments: list[str] | None = None) -> None:
    """Install or inspect execution storage using only the explicit API DSN."""
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
                install_backtest_execution_schema(connection)
            elif dict(connection.execute(CATALOG_SQL).fetchall()) != COLUMNS:
                raise BacktestExecutionStorageUnavailable(
                    "Backtest execution storage is missing or incompatible"
                )
    except (psycopg.Error, BacktestExecutionStorageUnavailable) as exc:
        parser.exit(
            1,
            f"Backtest execution storage {options.action} failed ({type(exc).__name__}).\n",
        )
    print("Backtest execution storage version 1 is available.")


if __name__ == "__main__":
    main()
