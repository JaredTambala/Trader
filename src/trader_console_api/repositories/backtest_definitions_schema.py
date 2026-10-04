"""Explicit installer for Console-owned immutable backtest definitions."""

from __future__ import annotations

from argparse import ArgumentParser
import os

import psycopg


COLUMNS = {
    "scope_id": "text",
    "definition_id": "uuid",
    "definition_version": "int4",
    "revision": "int4",
    "fingerprint": "text",
    "definition": "jsonb",
    "created_at": "timestamptz",
    "updated_at": "timestamptz",
}
CATALOG_SQL = """
SELECT column_name, udt_name FROM information_schema.columns
WHERE table_schema = 'console_app' AND table_name = 'backtest_definitions'
"""
INSTALL_SQL = """
CREATE TABLE IF NOT EXISTS console_app.backtest_definitions (
    scope_id text NOT NULL,
    definition_id uuid NOT NULL,
    definition_version integer NOT NULL DEFAULT 1 CHECK (definition_version = 1),
    revision integer NOT NULL CHECK (revision >= 1),
    fingerprint text NOT NULL CHECK (fingerprint ~ '^[0-9a-f]{64}$'),
    definition jsonb NOT NULL CHECK (jsonb_typeof(definition) = 'object'),
    created_at timestamptz NOT NULL DEFAULT transaction_timestamp(),
    updated_at timestamptz NOT NULL DEFAULT transaction_timestamp(),
    PRIMARY KEY (scope_id, definition_id, revision),
    UNIQUE (scope_id, fingerprint)
)
"""


class BacktestDefinitionStorageUnavailable(RuntimeError):
    """Definition storage is absent or incompatible; install it explicitly."""


def install_backtest_definition_schema(connection: psycopg.Connection) -> None:
    """Install only the additive definition table in the caller's transaction."""
    connection.execute("CREATE SCHEMA IF NOT EXISTS console_app")
    connection.execute(INSTALL_SQL)
    if dict(connection.execute(CATALOG_SQL).fetchall()) != COLUMNS:
        raise BacktestDefinitionStorageUnavailable(
            "Backtest definition storage has an incompatible column shape"
        )


def main(arguments: list[str] | None = None) -> None:
    """Install or inspect definition storage using only the explicit API DSN."""
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
                install_backtest_definition_schema(connection)
            elif dict(connection.execute(CATALOG_SQL).fetchall()) != COLUMNS:
                raise BacktestDefinitionStorageUnavailable(
                    "Backtest definition storage is missing or incompatible"
                )
    except (psycopg.Error, BacktestDefinitionStorageUnavailable) as exc:
        parser.exit(
            1,
            f"Backtest definition storage {options.action} failed ({type(exc).__name__}).\n",
        )
    print("Backtest definition storage version 1 is available.")


if __name__ == "__main__":
    main()
