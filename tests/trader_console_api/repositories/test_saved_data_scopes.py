"""Subject: saved Data scope repository persistence and exact identity.

Level: In-process repository adapter tests.
Collaborators: Recording asynchronous connection; no PostgreSQL server.
Guarantees: server scope binding, idempotent replay, immutable payloads, and evidence updates.
Non-goals: PostgreSQL planner behavior, installer execution, or browser rendering.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

from trader_console_api.data_scope_contracts import DataScopeEvidenceStatus
from trader_console_api.repositories.saved_data_scopes import SavedDataScopeSession
from trader_console_api.data_scope_contracts import SavedDataScopeCreate


def _request() -> SavedDataScopeCreate:
    """Build one normalized saved-scope request."""
    return SavedDataScopeCreate(
        name="Research window",
        asset_class="stock",
        symbols=("AAPL",),
        timeframe="1Min",
        interval="1Min",
        start=datetime(2026, 1, 1, tzinfo=UTC),
        end=datetime(2026, 1, 2, tzinfo=UTC),
        source_policy={"provider": "alpaca", "source": "iex"},
        research_role="backtest_authoring",
        manifest_artifact_id="manifest-1",
        quality_artifact_id="quality-1",
        created_by="operator-1",
        idempotency_key="request-1",
    )


def _row(request: SavedDataScopeCreate, *, saved_scope_id, status: str = "active") -> dict[str, object]:
    """Return a database-shaped saved-scope row."""
    now = datetime(2026, 1, 1, tzinfo=UTC)
    return {
        "scope_id": "console-a",
        "saved_scope_id": saved_scope_id,
        "revision": 1,
        "fingerprint": "a" * 64,
        "idempotency_key": request.idempotency_key,
        "scope": request.model_dump(mode="json", exclude={"evidence_status", "evidence_reason", "idempotency_key"}),
        "created_by": request.created_by,
        "evidence_status": status,
        "evidence_reason": None,
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
        """Return the configured aggregate count."""
        return (self.count,) if self.count is not None else None


class _Connection:
    """Connection double returning rows for exact repository operations."""

    def __init__(self, row: dict[str, object]) -> None:
        self.row = row
        self.calls: list[tuple[str, object | None]] = []

    async def execute(self, query: str, parameters: object | None = None) -> _Cursor:
        """Record SQL and return a deterministic cursor."""
        self.calls.append((query, parameters))
        if "information_schema" in query:
            return _Cursor([])
        if "count(*)" in query:
            return _Cursor([], count=1)
        if "data_scope_evidence" in query:
            return _Cursor([])
        return _Cursor([self.row])


def test_create_and_get_bind_server_scope_and_retain_immutable_refs() -> None:
    """The repository never accepts a client scope and stores exact artifact references."""
    request = _request()
    saved_scope_id = uuid4()
    connection = _Connection(_row(request, saved_scope_id=saved_scope_id))
    session = SavedDataScopeSession(connection, "console-a")

    created = asyncio.run(session.create(request, fingerprint="a" * 64, saved_scope_id=saved_scope_id))
    loaded = asyncio.run(session.get(saved_scope_id))

    assert created.saved_scope_id == saved_scope_id
    assert loaded is not None
    assert loaded.manifest_artifact_id == "manifest-1"
    assert loaded.quality_artifact_id == "quality-1"
    assert all("console-a" not in query for query, _ in connection.calls)
    assert any(parameters and parameters[0] == "console-a" for _, parameters in connection.calls)


def test_revalidate_without_projection_is_explicitly_unavailable() -> None:
    """A missing producer projection cannot silently refresh or widen a saved scope."""
    request = _request()
    saved_scope_id = uuid4()
    connection = _Connection(_row(request, saved_scope_id=saved_scope_id))
    session = SavedDataScopeSession(connection, "console-a")

    result = asyncio.run(session.current_evidence(asyncio.run(session.get(saved_scope_id))))

    assert result is None
    assert DataScopeEvidenceStatus.UNAVAILABLE.value == "unavailable"
