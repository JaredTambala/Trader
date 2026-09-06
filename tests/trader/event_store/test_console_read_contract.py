"""Contracts for the versioned Trader Console PostgreSQL read interface.

Subject: Console view allowlists, stable names, and compatibility negotiation.
Level: Deterministic event-store contract tests.
Collaborators: Producer-owned Console contract metadata and pure compatibility logic.
Guarantees: Read relations expose only reviewed fields and fail closed on incompatible versions.
Non-goals: Executing PostgreSQL DDL or defining deployment authorization policy.
"""

from contextlib import nullcontext
import re

import pytest

from trader.event_store.console_read_contract import (
    CONSOLE_READ_CONTRACT_VERSION,
    CONSOLE_READ_COLUMNS,
    CONSOLE_READ_SOURCES,
    assess_console_read_compatibility,
)


class _QueryResult:
    def fetchone(self) -> None:
        return None


class _RecordingConnection:
    def __init__(self) -> None:
        self.statements: list[str] = []

    def transaction(self) -> nullcontext[None]:
        return nullcontext()

    def execute(
        self, statement: object, parameters: object | None = None
    ) -> _QueryResult:
        del parameters
        rendered = statement if isinstance(statement, str) else statement.as_string()
        self.statements.append(rendered)
        return _QueryResult()


def test_console_read_contract_uses_explicit_allowlisted_columns() -> None:
    """Keep unrestricted configuration and payload fields outside the contract."""
    exposed_columns = {
        column
        for view_columns in CONSOLE_READ_COLUMNS.values()
        for column in view_columns
    }

    assert set(CONSOLE_READ_COLUMNS) == set(CONSOLE_READ_SOURCES)
    assert {
        "config_snapshot",
        "payload",
        "parameters",
        "assumptions",
        "provenance",
        "data_quality",
        "result_summary",
        "metadata",
        "decision_evidence",
        "value_payload",
    }.isdisjoint(exposed_columns)


@pytest.mark.parametrize(
    ("installed", "minimum", "consumer", "compatible", "reason"),
    [
        (1, 1, 1, True, None),
        (2, 1, 1, True, None),
        (2, 2, 1, False, "console_consumer_too_old"),
        (1, 1, 2, False, "console_read_contract_too_old"),
        (1, 2, 1, False, "console_read_contract_invalid"),
        (None, None, 1, False, "console_read_contract_missing"),
    ],
)
def test_console_read_compatibility_fails_closed(
    installed: int | None,
    minimum: int | None,
    consumer: int,
    compatible: bool,
    reason: str | None,
) -> None:
    """Admit only consumer versions covered by the installed compatibility range."""
    result = assess_console_read_compatibility(
        installed_version=installed,
        minimum_consumer_version=minimum,
        consumer_version=consumer,
    )

    assert result.compatible is compatible
    assert result.reason == reason
    assert result.consumer_version == consumer


def test_console_read_contract_version_starts_at_one() -> None:
    """Anchor the first additive Console database contract at version one."""
    assert CONSOLE_READ_CONTRACT_VERSION == 1


def test_console_read_relation_names_do_not_encode_contract_version() -> None:
    """Keep relation names stable while compatibility metadata carries version changes."""
    assert all(re.search(r"_v\d+$", name) is None for name in CONSOLE_READ_COLUMNS)


def test_install_plan_does_not_provision_database_authorization() -> None:
    """Keep roles, credentials, grants, and revocations outside contract installation."""
    from trader.event_store.console_read_contract import install_console_read_contract

    connection = _RecordingConnection()

    install_console_read_contract(connection)

    migration_sql = "\n".join(connection.statements).upper()
    assert "CREATE ROLE" not in migration_sql
    assert "ALTER ROLE" not in migration_sql
    assert "GRANT " not in migration_sql
    assert "REVOKE " not in migration_sql
