"""Explicit installation boundary for the paper operator command ledger.

Subject: Additive command-ledger installation and catalog validation.
Level: Repository unit tests.
Collaborators: Synchronous connection double and schema installer constants.
Guarantees: Installation is explicit, additive, and fails closed on shape drift.
Non-goals: PostgreSQL planner behavior, command admission, and HTTP routing.
"""

from __future__ import annotations

import pytest

from trader_console_api.repositories.paper_operator_commands_schema import (
    CATALOG_SQL,
    COLUMNS,
    INSTALL_SQL,
    PaperOperatorCommandStorageUnavailable,
    install_paper_operator_command_schema,
)


class _Cursor:
    def __init__(self, rows: list[tuple[str, str]]) -> None:
        self.rows = rows

    def fetchall(self) -> list[tuple[str, str]]:
        """Return configured catalog rows."""
        return self.rows


class _Connection:
    def __init__(self, rows: list[tuple[str, str]]) -> None:
        self.rows = rows
        self.statements: list[str] = []

    def execute(self, statement: str) -> _Cursor:
        """Record installer SQL and return configured catalog data."""
        self.statements.append(statement)
        return _Cursor(self.rows)


def test_install_is_explicit_and_catalog_checked() -> None:
    """Install only the command ledger and leave transaction ownership outside."""
    connection = _Connection(list(COLUMNS.items()))
    install_paper_operator_command_schema(connection)  # type: ignore[arg-type]
    assert connection.statements == [INSTALL_SQL, CATALOG_SQL]


def test_install_rejects_incompatible_existing_shape() -> None:
    """An incompatible relation is reported instead of silently repaired."""
    connection = _Connection([("scope_id", "integer")])
    with pytest.raises(PaperOperatorCommandStorageUnavailable, match="incompatible"):
        install_paper_operator_command_schema(connection)  # type: ignore[arg-type]
