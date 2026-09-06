"""Guarded PostgreSQL verification for the Trader Console read contract.

Subject: Installed Console views, stable relation names, compatibility, and rollback.
Level: PostgreSQL integration contract.
Collaborators: Guarded runtime database, real source tables, and Psycopg connections.
Guarantees: Installation projects allowlisted fields and exposes compatible metadata without provisioning IAM.
Non-goals: API transaction behavior, deployment authentication, roles, grants, or production IAM policy.
"""

from __future__ import annotations

from typing import Iterator

import pytest

from trader.event_store import PostgresEventStore
from trader.event_store.console_read_contract import (
    CONSOLE_READ_CONTRACT,
    CONSOLE_READ_VERSION_QUERY,
    inspect_console_read_contract,
    install_console_read_contract,
    rollback_console_read_contract,
)


pytestmark = pytest.mark.postgres


@pytest.fixture
def installed_console_read_contract(
    postgres_event_store: PostgresEventStore,
) -> Iterator[PostgresEventStore]:
    """Install and remove the contract using the guarded test database owner."""
    connection = postgres_event_store.connection()
    if connection.execute("SELECT to_regnamespace('console_read')").fetchone() != (
        None,
    ):
        pytest.skip("guarded test database already contains console_read")
    install_console_read_contract(connection)
    try:
        yield postgres_event_store
    finally:
        rollback_console_read_contract(connection)


def test_console_contract_projects_safe_fields_with_stable_names(
    installed_console_read_contract: PostgresEventStore,
) -> None:
    """Read approved data through stable views while excluded fields remain absent."""
    connection = installed_console_read_contract.connection()
    connection.execute(
        """
        INSERT INTO trading_sessions (
            session_id, strategy_id, status, config_snapshot, mode, symbols
        ) VALUES (%s, %s, %s, %s, %s, %s)
        """,
        [
            "session_console_contract",
            "strategy_demo",
            "running",
            '{"secret": "not-for-console"}',
            "paper",
            ["AAPL"],
        ],
    )

    row = connection.execute(
        """
        SELECT session_id, strategy_id, status, mode, symbols
        FROM console_read.sessions
        WHERE session_id = %s
        """,
        ["session_console_contract"],
    ).fetchone()
    columns = connection.execute(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = 'console_read' AND table_name = 'sessions'
        ORDER BY ordinal_position
        """
    ).fetchall()

    assert row == (
        "session_console_contract",
        "strategy_demo",
        "running",
        "paper",
        ["AAPL"],
    )
    assert "config_snapshot" not in {column[0] for column in columns}


def test_console_contract_reports_compatible_catalog_and_rolls_back(
    installed_console_read_contract: PostgresEventStore,
) -> None:
    """Verify current metadata and let fixture teardown remove only the read schema."""
    connection = installed_console_read_contract.connection()

    inspection = inspect_console_read_contract(connection)
    version = connection.execute(
        CONSOLE_READ_VERSION_QUERY, [CONSOLE_READ_CONTRACT]
    ).fetchone()

    assert inspection.ready is True
    assert inspection.issues == ()
    assert version == (1, 1)
