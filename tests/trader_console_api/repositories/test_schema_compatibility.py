"""Contracts for Console database-schema compatibility inspection.

Subject: Pure and repository-backed assessment of the configured database schema.
Level: In-process unit and adapter contract.
Collaborators: Real compatibility logic with a recording asynchronous connection; no PostgreSQL server.
Guarantees: Metadata admission, exact allowlisted catalog shape, and parameterized inspection remain deterministic.
Non-goals: Producer migrations, role policy, query plans, and live connection-pool behavior.
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import Any

from trader_console_api.repositories.schema_compatibility import (
    EXPECTED_CONTRACT_COLUMNS,
    SchemaCompatibilityRepository,
    assess_schema_compatibility,
)


def _catalog_rows() -> list[tuple[str, str]]:
    return [
        (relation_name, column_name)
        for relation_name, columns in EXPECTED_CONTRACT_COLUMNS.items()
        for column_name in columns
    ]


class _Cursor:
    def __init__(self, row: tuple[int, int] | None = None, rows: list[tuple[str, str]] | None = None) -> None:
        self._row = row
        self._rows = rows or []

    async def fetchone(self) -> tuple[int, int] | None:
        return self._row

    async def fetchall(self) -> list[tuple[str, str]]:
        return self._rows


class _RecordingConnection:
    def __init__(self) -> None:
        self.calls: list[tuple[str, object | None]] = []

    async def execute(self, query: str, parameters: object | None = None) -> _Cursor:
        self.calls.append((query, parameters))
        if "contract_version" in query:
            return _Cursor(row=(1, 1))
        return _Cursor(rows=_catalog_rows())


class _RecordingDatabase:
    def __init__(self, connection: _RecordingConnection) -> None:
        self._connection = connection

    @asynccontextmanager
    async def transaction(self) -> Any:
        yield self._connection


def test_exact_catalog_and_compatible_metadata_are_ready() -> None:
    """Admit the installed schema when every stable relation has its exact projection."""
    inspection = assess_schema_compatibility(
        version_row=(1, 1),
        catalog_rows=_catalog_rows(),
    )

    assert inspection.ready
    assert inspection.issues == ()


def test_newer_additive_schema_can_admit_the_current_consumer() -> None:
    """Allow newer metadata when its minimum consumer remains compatible with this API."""
    inspection = assess_schema_compatibility(
        version_row=(2, 1),
        catalog_rows=_catalog_rows(),
    )

    assert inspection.ready
    assert inspection.installed_version == 2


def test_older_database_schema_fails_with_stable_issue_code() -> None:
    """Reject a database schema older than the API's supported version."""
    inspection = assess_schema_compatibility(
        version_row=(0, 0),
        catalog_rows=_catalog_rows(),
    )

    assert not inspection.ready
    assert "database_schema_too_old" in inspection.issues


def test_missing_allowlisted_column_fails_catalog_admission() -> None:
    """Reject silent producer drift before the API begins serving requests."""
    rows = [row for row in _catalog_rows() if row != ("sessions", "status")]

    inspection = assess_schema_compatibility(version_row=(1, 1), catalog_rows=rows)

    assert "schema_catalog_mismatch:sessions" in inspection.issues


def test_repository_parameterizes_schema_identity_and_performs_reads_only() -> None:
    """Keep readiness SQL fixed, parameterized, and free from database mutation statements."""
    connection = _RecordingConnection()

    repository = SchemaCompatibilityRepository(_RecordingDatabase(connection))

    inspection = asyncio.run(repository.inspect())

    assert inspection.ready
    assert any(parameters == ["trader_console"] for _query, parameters in connection.calls)
    sql_text = " ".join(query.upper() for query, _parameters in connection.calls)
    for mutation in ("INSERT ", "UPDATE ", "DELETE ", "CREATE ", "ALTER ", "DROP "):
        assert mutation not in sql_text
