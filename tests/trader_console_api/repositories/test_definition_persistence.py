"""Scoped persistence contracts for immutable Console backtest definitions.

Subject: Definition repository SQL boundaries, scope binding, and revision append semantics.
Level: In-process repository adapter.
Collaborators: Recording asynchronous connection; no PostgreSQL server.
Guarantees: Client values remain parameters, latest revisions are readable, and writes append rows.
Non-goals: PostgreSQL locking/planner behavior, installer DDL, and HTTP serialization.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

from trader_console_api.contracts import BacktestDefinition
from trader_console_api.data_scope_contracts import BacktestDataScopeHandoff, DataScopeEvidenceStatus, DataScopeSourcePolicy
from trader_console_api.repositories.backtest_definitions import BacktestDefinitionSession
from tests.trader_console_api.support import implementation_lineage


def _definition(name: str = "Smoke") -> BacktestDefinition:
    """Build one normalized definition-shaped value for persistence cases."""
    return BacktestDefinition(
        display_name=name,
        strategy_profile_id="noop",
        strategy_catalogue_version="standard-1",
        strategy_implementation_lineage=implementation_lineage(),
        risk_profile_id="noop",
        risk_catalogue_version="standard-1",
        risk_implementation_lineage=implementation_lineage(kind="risk", suffix="risk"),
        asset_class="stock",
        symbols=("AAPL",),
        timeframe="1Min",
        start=datetime(2026, 1, 1, tzinfo=UTC),
        end=datetime(2026, 1, 1, 1, tzinfo=UTC),
        initial_cash=100_000,
        data_scope=BacktestDataScopeHandoff(
            saved_scope_id="00000000-0000-0000-0000-000000000001", fingerprint="a" * 64,
            asset_class="stock", symbols=("AAPL",), timeframe="1Min", interval="1Min",
            start=datetime(2026, 1, 1, tzinfo=UTC), end=datetime(2026, 1, 1, 1, tzinfo=UTC),
            source_policy=DataScopeSourcePolicy(provider="fixture", source="fixture"),
            manifest_artifact_id="manifest-1", quality_artifact_id="quality-1",
            evidence_status=DataScopeEvidenceStatus.ACTIVE,
        ),
    )


def _row(definition: BacktestDefinition, *, definition_id, revision: int) -> dict[str, object]:
    """Return a producer-shaped row with nested JSON definition data."""
    now = datetime(2026, 1, 1, tzinfo=UTC)
    return {
        "scope_id": "scope-a",
        "definition_id": definition_id,
        "definition_version": 1,
        "revision": revision,
        "fingerprint": "a" * 64,
        "definition": definition.model_dump(mode="json"),
        "created_at": now,
        "updated_at": now,
    }


class _Cursor:
    """Async cursor with named columns for repository normalization."""

    def __init__(self, rows: list[dict[str, object]], *, count: int | None = None) -> None:
        self.rows = rows
        self.count = count
        names = tuple(rows[0]) if rows else ()
        self.description = [SimpleNamespace(name=name) for name in names]

    async def fetchall(self) -> list[tuple[object, ...]]:
        """Return rows in cursor column order."""
        return [tuple(row.values()) for row in self.rows]

    async def fetchone(self) -> tuple[int] | None:
        """Return one aggregate count."""
        return (self.count,) if self.count is not None else None


class _Connection:
    """Connection double that returns configured rows for select/insert calls."""

    def __init__(self, rows: list[dict[str, object]]) -> None:
        self.rows = rows
        self.calls: list[tuple[str, object | None]] = []

    async def execute(self, query: str, parameters: object | None = None) -> _Cursor:
        """Record parameterized SQL and return deterministic cursor data."""
        self.calls.append((query, parameters))
        if "count(DISTINCT" in query:
            return _Cursor([], count=len(self.rows))
        if "INSERT INTO" in query:
            return _Cursor([self.rows[-1]])
        return _Cursor([self.rows[0]])


def test_create_and_get_bind_scope_and_store_normalized_json() -> None:
    """Create and read keep scope server-owned while storing a typed JSON document."""
    definition = _definition()
    definition_id = uuid4()
    connection = _Connection([_row(definition, definition_id=definition_id, revision=1)])
    session = BacktestDefinitionSession(connection, "scope-a")

    created = asyncio.run(session.create(definition, fingerprint="a" * 64, definition_id=definition_id))
    loaded = asyncio.run(session.get(definition_id))

    assert created.definition_id == str(definition_id)
    assert loaded is not None
    assert loaded.definition.symbols == ("AAPL",)
    query, parameters = connection.calls[0]
    assert "scope-a" not in query
    assert parameters[0] == "scope-a"
    assert parameters[-2] == "a" * 64


def test_create_revision_reads_latest_and_appends_next_revision() -> None:
    """Revision creation never updates the prior row and chooses the next number."""
    definition_id = uuid4()
    first = _definition()
    second = _definition("Second")
    connection = _Connection([
        _row(first, definition_id=definition_id, revision=1),
        _row(second, definition_id=definition_id, revision=2),
    ])
    session = BacktestDefinitionSession(connection, "scope-a")

    created = asyncio.run(
        session.create_revision(definition_id, second, fingerprint="b" * 64)
    )

    assert created.revision == 2
    assert any("INSERT INTO console_app.backtest_definitions" in query for query, _ in connection.calls)
    assert not any("UPDATE console_app.backtest_definitions" in query for query, _ in connection.calls)
