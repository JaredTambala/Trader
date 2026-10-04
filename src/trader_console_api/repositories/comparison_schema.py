"""Explicit, additive installer for Console-owned comparison definitions.

This module has no runtime execution dependency. API startup never calls it.
"""

from __future__ import annotations

from argparse import ArgumentParser
import os

import psycopg


COLUMNS = {
    "scope_id": "text", "experiment_id": "text", "view_id": "uuid",
    "definition_version": "int4", "definition": "jsonb", "revision": "int4",
    "created_at": "timestamptz", "updated_at": "timestamptz",
}
CATALOG_SQL = """
SELECT column_name, udt_name FROM information_schema.columns
WHERE table_schema = 'console_app' AND table_name = 'comparison_views'
"""
INSTALL_SQL = """
CREATE TABLE IF NOT EXISTS console_app.comparison_views (
    scope_id text NOT NULL,
    experiment_id text NOT NULL,
    view_id uuid NOT NULL,
    definition_version integer NOT NULL DEFAULT 1 CHECK (definition_version = 1),
    definition jsonb NOT NULL CHECK (jsonb_typeof(definition) = 'object'),
    revision integer NOT NULL DEFAULT 1 CHECK (revision >= 1),
    created_at timestamptz NOT NULL DEFAULT transaction_timestamp(),
    updated_at timestamptz NOT NULL DEFAULT transaction_timestamp(),
    PRIMARY KEY (scope_id, experiment_id, view_id)
)
"""


class ComparisonStorageUnavailable(RuntimeError):
    """Comparison storage is absent or incompatible; install it explicitly."""


def install_comparison_schema(connection: psycopg.Connection) -> None:
    """Install only the additive application table in the caller's transaction.

    Existing rows and producer schemas are untouched. Unknown column shapes
    are refused rather than repaired. The caller owns commit or rollback.
    """
    connection.execute("CREATE SCHEMA IF NOT EXISTS console_app")
    connection.execute(INSTALL_SQL)
    if dict(connection.execute(CATALOG_SQL).fetchall()) != COLUMNS:
        raise ComparisonStorageUnavailable("Comparison storage has an incompatible column shape")


def main(arguments: list[str] | None = None) -> None:
    """Install or inspect the application table using only the explicit API DSN."""
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
                install_comparison_schema(connection)
            elif dict(connection.execute(CATALOG_SQL).fetchall()) != COLUMNS:
                raise ComparisonStorageUnavailable("Comparison storage is missing or incompatible")
    except (psycopg.Error, ComparisonStorageUnavailable) as exc:
        parser.exit(1, f"Comparison storage {options.action} failed ({type(exc).__name__}).\n")
    print("Comparison storage version 1 is available.")


if __name__ == "__main__":
    main()
