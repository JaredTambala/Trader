"""Subject: explicit installation boundary for Console comparison storage.

Level: Repository unit tests.
Collaborators: A synchronous connection double; schema installer constants.
Guarantees: Installation is additive, validates the expected catalog shape, and
does not hide a commit inside the installer.
Non-goals: PostgreSQL planner behavior, migration tooling, and HTTP routes.
"""

from __future__ import annotations

import pytest

from trader_console_api.repositories.comparison_schema import (
    CATALOG_SQL,
    COLUMNS,
    INSTALL_SQL,
    ComparisonStorageUnavailable,
    install_comparison_schema,
)


class _Cursor:
    """Tiny synchronous cursor result for catalog inspection."""

    def __init__(self, rows: list[tuple[str, str]]) -> None:
        self.rows = rows

    def fetchall(self) -> list[tuple[str, str]]:
        """Return the configured catalog rows."""
        return self.rows


class _Connection:
    """Connection double that records SQL without providing transaction methods."""

    def __init__(self, rows: list[tuple[str, str]]) -> None:
        self.rows = rows
        self.statements: list[str] = []

    def execute(self, statement: str):
        """Record SQL and return catalog rows for catalog queries."""
        self.statements.append(statement)
        return _Cursor(self.rows)


def test_install_is_explicit_and_catalog_checked() -> None:
    """Installer creates the application table and checks its resulting shape."""
    connection = _Connection(list(COLUMNS.items()))

    install_comparison_schema(connection)

    assert connection.statements[:2] == [
        "CREATE SCHEMA IF NOT EXISTS console_app",
        INSTALL_SQL,
    ]
    assert connection.statements[-1] == CATALOG_SQL


def test_install_rejects_an_incompatible_existing_shape() -> None:
    """Installer fails closed instead of altering an incompatible relation."""
    connection = _Connection([("scope_id", "integer")])

    with pytest.raises(ComparisonStorageUnavailable, match="incompatible"):
        install_comparison_schema(connection)
