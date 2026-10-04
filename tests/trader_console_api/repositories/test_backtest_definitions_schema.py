"""Explicit installation boundary for immutable Console backtest definitions.

Subject: Additive definition-storage installation and catalog validation.
Level: Repository unit tests.
Collaborators: Synchronous connection double and schema installer constants.
Guarantees: Installation is explicit, additive, and fails closed on shape drift.
Non-goals: PostgreSQL planner behavior, revision writes, and HTTP routing.
"""

from __future__ import annotations

import pytest

from trader_console_api.repositories.backtest_definitions_schema import (
    CATALOG_SQL,
    COLUMNS,
    INSTALL_SQL,
    BacktestDefinitionStorageUnavailable,
    install_backtest_definition_schema,
)


class _Cursor:
    """Tiny synchronous cursor result for catalog inspection."""

    def __init__(self, rows: list[tuple[str, str]]) -> None:
        self.rows = rows

    def fetchall(self) -> list[tuple[str, str]]:
        """Return configured catalog rows."""
        return self.rows


class _Connection:
    """Connection double that records installer SQL."""

    def __init__(self, rows: list[tuple[str, str]]) -> None:
        self.rows = rows
        self.statements: list[str] = []

    def execute(self, statement: str) -> _Cursor:
        """Record statement and return the configured catalog result."""
        self.statements.append(statement)
        return _Cursor(self.rows)


def test_install_is_explicit_and_catalog_checked() -> None:
    """Installer creates only the additive table and leaves commit ownership outside."""
    connection = _Connection(list(COLUMNS.items()))

    install_backtest_definition_schema(connection)  # type: ignore[arg-type]

    assert connection.statements[:2] == [
        "CREATE SCHEMA IF NOT EXISTS console_app",
        INSTALL_SQL,
    ]
    assert connection.statements[-1] == CATALOG_SQL


def test_install_rejects_incompatible_existing_shape() -> None:
    """An existing incompatible relation is reported instead of altered silently."""
    connection = _Connection([("scope_id", "integer")])

    with pytest.raises(BacktestDefinitionStorageUnavailable, match="incompatible"):
        install_backtest_definition_schema(connection)  # type: ignore[arg-type]
