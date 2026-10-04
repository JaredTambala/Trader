"""Explicit installer for immutable Console saved data scopes."""

from __future__ import annotations

from argparse import ArgumentParser
import os

import psycopg


COLUMNS = {
    "scope_id": "text",
    "saved_scope_id": "uuid",
    "revision": "int4",
    "fingerprint": "text",
    "idempotency_key": "text",
    "scope": "jsonb",
    "created_by": "text",
    "evidence_status": "text",
    "evidence_reason": "text",
    "created_at": "timestamptz",
    "updated_at": "timestamptz",
}
CATALOG_SQL = """
SELECT column_name, udt_name FROM information_schema.columns
WHERE table_schema = 'console_app' AND table_name = 'saved_data_scopes'
"""
INSTALL_SQL = """
CREATE TABLE IF NOT EXISTS console_app.saved_data_scopes (
    scope_id text NOT NULL,
    saved_scope_id uuid NOT NULL,
    revision integer NOT NULL DEFAULT 1 CHECK (revision = 1),
    fingerprint text NOT NULL CHECK (fingerprint ~ '^[0-9a-f]{64}$'),
    idempotency_key text NOT NULL CHECK (length(idempotency_key) BETWEEN 1 AND 200),
    scope jsonb NOT NULL CHECK (jsonb_typeof(scope) = 'object'),
    created_by text NOT NULL CHECK (length(created_by) BETWEEN 1 AND 200),
    evidence_status text NOT NULL CHECK (evidence_status IN ('active', 'stale', 'unavailable')),
    evidence_reason text,
    created_at timestamptz NOT NULL DEFAULT transaction_timestamp(),
    updated_at timestamptz NOT NULL DEFAULT transaction_timestamp(),
    PRIMARY KEY (scope_id, saved_scope_id),
    UNIQUE (scope_id, fingerprint),
    UNIQUE (scope_id, idempotency_key)
)
"""


class SavedDataScopeStorageUnavailable(RuntimeError):
    """Saved-scope storage is absent or incompatible; install it explicitly."""


def install_saved_data_scope_schema(connection: psycopg.Connection) -> None:
    """Install the additive saved-scope table in the caller's transaction."""
    connection.execute("CREATE SCHEMA IF NOT EXISTS console_app")
    connection.execute(INSTALL_SQL)
    if dict(connection.execute(CATALOG_SQL).fetchall()) != COLUMNS:
        raise SavedDataScopeStorageUnavailable(
            "Saved data scope storage has an incompatible column shape"
        )


def main(arguments: list[str] | None = None) -> None:
    """Install or inspect saved-scope storage using the explicit API DSN."""
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
                install_saved_data_scope_schema(connection)
            elif dict(connection.execute(CATALOG_SQL).fetchall()) != COLUMNS:
                raise SavedDataScopeStorageUnavailable(
                    "Saved data scope storage is missing or incompatible"
                )
    except (psycopg.Error, SavedDataScopeStorageUnavailable) as exc:
        parser.exit(
            1,
            f"Saved data scope storage {options.action} failed ({type(exc).__name__}).\n",
        )
    print("Saved data scope storage version 1 is available.")


if __name__ == "__main__":
    main()
