"""Console data-to-backtest contract qualification.

Subject: The API path from an exact saved Data scope to a durable backtest
command.
Level: In-process cross-package workflow using the real FastAPI routers and
application services with deterministic persistence doubles.
Collaborators: Saved-scope, preflight, immutable-definition, and execution
services; maintained strategy catalogue; typed Console contracts.
Guarantees: Scope and manifest/quality identity survive reopen, preflight,
definition persistence, and command submission; server-side stale and changed
scope evidence blocks persistence before coverage or execution.
Non-goals: PostgreSQL SQL/installer behavior, the worker's producer adapter,
browser rendering, or replay-bar content identity owned by Data/research.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from uuid import UUID

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from trader_console_api.contracts import (
    BacktestDefinition,
    BacktestDefinitionRevision,
    BacktestExecutionRecord,
)
from trader_console_api.data_scope_contracts import (
    BacktestDataScopeHandoff,
    DataScopeEvidenceStatus,
    SavedDataScope,
    SavedDataScopeCreate,
)
from trader_console_api.repositories.backtest_executions import BacktestExecutionDefinitionNotFound
from trader_console_api.repositories.backtest_definitions import BacktestDefinitionNotFound
from trader_console_api.routers.backtest_definitions import router as definition_router
from trader_console_api.routers.backtest_executions import router as execution_router
from trader_console_api.routers.catalogue import router as catalogue_router
from trader_console_api.routers.saved_data_scopes import router as saved_scope_router
from trader_console_api.services.backtest_definitions import BacktestDefinitionService
from trader_console_api.services.backtest_executions import BacktestExecutionService
from trader_console_api.services.catalogue import PreflightService
from trader_console_api.services.saved_data_scopes import SavedDataScopeService
from trader_standard.catalogue import maintained_catalogue
from tests.trader_console_api.support import implementation_lineage


NOW = datetime(2026, 6, 21, 0, 0, tzinfo=UTC)
SCOPE_ID = UUID("00000000-0000-0000-0000-000000000001")
DEFINITION_ID = UUID("00000000-0000-0000-0000-000000000002")
EXECUTION_ID = UUID("00000000-0000-0000-0000-000000000003")
SERVER_SCOPE_ID = "console-local"


class _ScopeStore:
    """Deterministic store shared by scope sessions in one workflow."""

    def __init__(self) -> None:
        self.scope: SavedDataScope | None = None


class _ScopeSession:
    """Minimal saved-scope repository session for application-service tests."""

    def __init__(self, store: _ScopeStore) -> None:
        self._store = store

    async def require_storage(self) -> None:
        """Represent explicitly installed scope storage."""

    async def create(
        self,
        request: SavedDataScopeCreate,
        *,
        fingerprint: str,
        saved_scope_id: UUID | None = None,
    ) -> SavedDataScope:
        """Persist one immutable scope or replay its exact identity."""
        if self._store.scope is not None:
            if self._store.scope.fingerprint != fingerprint:
                raise ValueError("saved scope identity conflict")
            return self._store.scope
        payload = request.model_dump()
        payload.update(
            {
                "saved_scope_id": saved_scope_id or SCOPE_ID,
                "scope_id": SERVER_SCOPE_ID,
                "revision": 1,
                "fingerprint": fingerprint,
                "created_at": NOW,
                "updated_at": NOW,
            }
        )
        self._store.scope = SavedDataScope.model_validate(payload)
        return self._store.scope

    async def get(self, saved_scope_id: UUID) -> SavedDataScope | None:
        """Return only the saved scope in the server-owned Console scope."""
        scope = self._store.scope
        return scope if scope is not None and scope.saved_scope_id == saved_scope_id else None

    async def list(self, limit: int, offset: int) -> tuple[list[SavedDataScope], int]:
        """Return a bounded page of the one fixture scope."""
        items = [self._store.scope] if self._store.scope is not None else []
        return items[offset : offset + limit], len(items)

    async def current_evidence(
        self, scope: SavedDataScope
    ) -> tuple[DataScopeEvidenceStatus, str | None] | None:
        """Return no producer projection; revalidation is outside this workflow."""
        return None

    async def update_evidence(
        self,
        saved_scope_id: UUID,
        *,
        status: DataScopeEvidenceStatus,
        reason: str | None,
    ) -> SavedDataScope | None:
        """Apply only the mutable evidence qualification state."""
        scope = await self.get(saved_scope_id)
        if scope is None:
            return None
        self._store.scope = scope.model_copy(
            update={"evidence_status": status, "evidence_reason": reason, "updated_at": NOW}
        )
        return self._store.scope


class _ScopeRepository:
    """Async repository boundary backed by one isolated test store."""

    def __init__(self, store: _ScopeStore) -> None:
        self._store = store

    @asynccontextmanager
    async def session(self, *, write: bool = False) -> AsyncIterator[_ScopeSession]:
        """Yield a scope session without opening a database connection."""
        del write
        yield _ScopeSession(self._store)


class _CoverageRepository:
    """Bounded coverage adapter used by the real preflight service."""

    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    async def backtest_coverage(self, **kwargs: object) -> list[dict[str, object]]:
        """Return deterministic warmup and replay coverage for the exact scope."""
        self.calls.append(kwargs)
        return [
            {
                "symbol": "BTC/USD",
                "asset_class": "crypto",
                "timeframe": "1Min",
                "first_ts": datetime(2026, 6, 20, 23, 39, tzinfo=UTC),
                "last_ts": datetime(2026, 6, 21, 0, 30, tzinfo=UTC),
                "bar_count": 52,
            }
        ]


class _DefinitionStore:
    """Deterministic immutable-definition store shared with command storage."""

    def __init__(self) -> None:
        self.revision: BacktestDefinitionRevision | None = None


class _DefinitionSession:
    """Minimal repository session for definition service orchestration."""

    def __init__(self, store: _DefinitionStore) -> None:
        self._store = store

    async def require_storage(self) -> None:
        """Represent explicitly installed definition storage."""

    async def create(
        self,
        definition: BacktestDefinition,
        *,
        fingerprint: str,
        definition_id: UUID | None = None,
    ) -> BacktestDefinitionRevision:
        """Persist one normalized immutable revision."""
        revision = BacktestDefinitionRevision(
            definition_id=str(definition_id or DEFINITION_ID),
            scope_id=SERVER_SCOPE_ID,
            revision=1,
            fingerprint=fingerprint,
            definition=definition,
            created_at=NOW,
            updated_at=NOW,
        )
        self._store.revision = revision
        return revision

    async def get(
        self, definition_id: UUID, *, revision: int | None = None
    ) -> BacktestDefinitionRevision | None:
        """Return the requested latest or exact immutable revision."""
        value = self._store.revision
        if value is None or UUID(value.definition_id) != definition_id:
            return None
        return value if revision is None or value.revision == revision else None

    async def list(self, limit: int, offset: int) -> tuple[list[BacktestDefinitionRevision], int]:
        """Return a bounded page of stored definitions."""
        items = [self._store.revision] if self._store.revision is not None else []
        return items[offset : offset + limit], len(items)

    async def create_revision(
        self,
        definition_id: UUID,
        definition: BacktestDefinition,
        *,
        fingerprint: str,
    ) -> BacktestDefinitionRevision:
        """Append a new immutable revision after requiring the identity."""
        current = await self.get(definition_id)
        if current is None:
            raise BacktestDefinitionNotFound("Backtest definition not found")
        revision = current.model_copy(
            update={
                "revision": current.revision + 1,
                "fingerprint": fingerprint,
                "definition": definition,
                "updated_at": NOW,
            }
        )
        self._store.revision = revision
        return revision


class _DefinitionRepository:
    """Async repository boundary backed by one isolated test store."""

    def __init__(self, store: _DefinitionStore) -> None:
        self._store = store

    @asynccontextmanager
    async def session(self, *, write: bool = False) -> AsyncIterator[_DefinitionSession]:
        """Yield a definition session without opening a database connection."""
        del write
        yield _DefinitionSession(self._store)


class _ExecutionStore:
    """Durable command store linked to the immutable definition fixture."""

    def __init__(self, definitions: _DefinitionStore) -> None:
        self._definitions = definitions
        self.record: BacktestExecutionRecord | None = None


class _ExecutionSession:
    """Minimal repository session for command submit/status behavior."""

    def __init__(self, store: _ExecutionStore) -> None:
        self._store = store

    async def require_storage(self) -> None:
        """Represent explicitly installed execution storage."""

    async def submit(
        self, definition_id: UUID, *, idempotency_key: str
    ) -> BacktestExecutionRecord:
        """Create one queued command, replaying an identical idempotency key."""
        definition = self._store._definitions.revision
        if definition is None or UUID(definition.definition_id) != definition_id:
            raise BacktestExecutionDefinitionNotFound("Backtest definition not found")
        if self._store.record is not None:
            if self._store.record.idempotency_key == idempotency_key:
                return self._store.record
            raise ValueError("execution idempotency conflict")
        self._store.record = BacktestExecutionRecord(
            execution_id=str(EXECUTION_ID),
            scope_id=SERVER_SCOPE_ID,
            definition_id=definition.definition_id,
            definition_revision=definition.revision,
            definition_fingerprint=definition.fingerprint,
            idempotency_key=idempotency_key,
            status="queued",
            attempt=0,
            processed_cycles=0,
            created_at=NOW,
        )
        return self._store.record

    async def get(self, execution_id: UUID) -> BacktestExecutionRecord | None:
        """Return the durable command in the configured scope."""
        record = self._store.record
        return record if record is not None and UUID(record.execution_id) == execution_id else None

    async def list(self, limit: int, offset: int) -> tuple[list[BacktestExecutionRecord], int]:
        """Return a bounded command history page."""
        items = [self._store.record] if self._store.record is not None else []
        return items[offset : offset + limit], len(items)


class _ExecutionRepository:
    """Async repository boundary backed by one isolated test store."""

    def __init__(self, store: _ExecutionStore) -> None:
        self._store = store

    @asynccontextmanager
    async def session(self, *, write: bool = False) -> AsyncIterator[_ExecutionSession]:
        """Yield an execution session without opening a database connection."""
        del write
        yield _ExecutionSession(self._store)


def _application() -> tuple[FastAPI, _ScopeStore, _DefinitionStore, _ExecutionStore, _CoverageRepository]:
    """Compose real API routers/services over isolated deterministic stores."""
    scopes = _ScopeStore()
    definitions = _DefinitionStore()
    executions = _ExecutionStore(definitions)
    coverage = _CoverageRepository()
    scope_service = SavedDataScopeService(_ScopeRepository(scopes))
    preflight_service = PreflightService(
        coverage,
        maintained_catalogue(),
        saved_scope_lookup=scope_service,
    )
    definition_service = BacktestDefinitionService(
        _DefinitionRepository(definitions), preflight_service
    )
    execution_service = BacktestExecutionService(_ExecutionRepository(executions))
    app = FastAPI()
    app.include_router(saved_scope_router)
    app.include_router(catalogue_router)
    app.include_router(definition_router)
    app.include_router(execution_router)
    app.state.saved_data_scope_service = scope_service
    app.state.preflight_service = preflight_service
    app.state.backtest_definition_service = definition_service
    app.state.backtest_execution_service = execution_service
    return app, scopes, definitions, executions, coverage


def _scope_request() -> dict[str, object]:
    """Return one exact, instrument-agnostic fixture scope request."""
    return {
        "name": "Qualified research scope",
        "asset_class": "crypto",
        "symbols": ["BTC/USD"],
        "universe": None,
        "timeframe": "1Min",
        "interval": "1Min",
        "start": NOW.isoformat(),
        "end": datetime(2026, 6, 21, 0, 30, tzinfo=UTC).isoformat(),
        "source_policy": {"provider": "fixture", "source": "fixture", "allow_fallback": False},
        "research_role": "backtest_authoring",
        "manifest_artifact_id": "manifest-1",
        "quality_artifact_id": "quality-1",
        "evidence_status": "active",
        "evidence_reason": None,
        "created_by": "console-operator",
        "idempotency_key": "scope-key-1",
    }


def _handoff(scope: SavedDataScope) -> dict[str, object]:
    """Project the saved-scope response into the authoring handoff contract."""
    return BacktestDataScopeHandoff(
        saved_scope_id=scope.saved_scope_id,
        fingerprint=scope.fingerprint,
        asset_class=scope.asset_class,
        symbols=scope.symbols,
        universe=scope.universe,
        timeframe=scope.timeframe,
        interval=scope.interval,
        start=scope.start,
        end=scope.end,
        source_policy=scope.source_policy,
        manifest_artifact_id=scope.manifest_artifact_id,
        quality_artifact_id=scope.quality_artifact_id,
        evidence_status=scope.evidence_status,
        evidence_reason=scope.evidence_reason,
    ).model_dump(mode="json")


def _draft(scope: SavedDataScope, *, handoff: dict[str, object] | None = None) -> dict[str, object]:
    """Build one valid authoring request carrying exact scope and admission evidence."""
    return {
        "display_name": "Qualified fixture backtest",
        "strategy_profile_id": "bollinger_band",
        "strategy_catalogue_version": "standard-1",
        "strategy_parameters": {"period": 20, "stddev_multiplier": 2, "target_qty_when_long": 0.01},
        "strategy_implementation_lineage": implementation_lineage("bollinger_band").model_dump(mode="json"),
        "risk_profile_id": "max_orders_per_run",
        "risk_catalogue_version": "standard-1",
        "risk_parameters": {"limit": 10},
        "risk_implementation_lineage": implementation_lineage(
            "max_orders_per_run", kind="risk", suffix="max-orders"
        ).model_dump(mode="json"),
        "asset_class": scope.asset_class,
        "symbols": list(scope.symbols),
        "timeframe": scope.timeframe,
        "start": scope.start.isoformat(),
        "end": scope.end.isoformat(),
        "initial_cash": 100_000,
        "initial_positions": [],
        "assumptions": {"allow_price_carry_forward": False},
        "benchmark_id": "buy_hold",
        "data_scope": handoff if handoff is not None else _handoff(scope),
    }


def _create_scope(client: TestClient) -> SavedDataScope:
    """Create and reopen the exact scope through the public HTTP routes."""
    created = client.post("/api/data-scopes", json=_scope_request())
    assert created.status_code == 201
    body = created.json()
    reopened = client.get(f"/api/data-scopes/{body['saved_scope_id']}")
    assert reopened.status_code == 200
    assert reopened.json()["fingerprint"] == body["fingerprint"]
    assert reopened.json()["manifest_artifact_id"] == "manifest-1"
    assert reopened.json()["quality_artifact_id"] == "quality-1"
    return SavedDataScope.model_validate(reopened.json())


def test_exact_scope_survives_authoring_persistence_and_execution_submit() -> None:
    """Preserve Data evidence identity from saved scope through command status."""
    app, scopes, definitions, executions, coverage = _application()
    with TestClient(app) as client:
        scope = _create_scope(client)
        handoff = _handoff(scope)
        draft = _draft(scope, handoff=handoff)

        preflight = client.post("/api/backtests/preflight", json=draft)
        assert preflight.status_code == 200
        assert preflight.json()["valid"] is True
        assert preflight.json()["normalized_definition"]["data_scope"] == handoff
        assert coverage.calls[-1]["symbols"] == ("BTC/USD",)

        created = client.post("/api/backtests/definitions", json=draft)
        assert created.status_code == 201
        definition = created.json()
        assert definition["definition"]["data_scope"] == handoff
        assert definitions.revision is not None
        assert definitions.revision.definition.data_scope.model_dump(mode="json") == handoff
        assert scopes.scope is not None
        assert scopes.scope.fingerprint == handoff["fingerprint"]

        submitted = client.post(
            "/api/backtests/executions",
            json={"definition_id": definition["definition_id"], "idempotency_key": "execution-key-1"},
        )
        assert submitted.status_code == 202
        assert submitted.json()["status"] == "queued"
        assert submitted.json()["definition_id"] == definition["definition_id"]
        assert submitted.json()["definition_fingerprint"] == definition["fingerprint"]

        status = client.get(f"/api/backtests/executions/{submitted.json()['execution_id']}")
        assert status.status_code == 200
        assert status.json() == submitted.json()
        assert executions.record is not None
        assert executions.record.definition_fingerprint == definition["fingerprint"]


@pytest.mark.parametrize("blocker", ["stale", "mismatch"])
def test_scope_blockers_stop_definition_persistence_before_execution(
    blocker: str,
) -> None:
    """Reject stale or changed server evidence with actionable preflight issues."""
    app, scopes, definitions, _executions, coverage = _application()
    with TestClient(app) as client:
        scope = _create_scope(client)
        handoff = _handoff(scope)
        draft = _draft(scope, handoff=handoff)
        if blocker == "stale":
            assert scopes.scope is not None
            scopes.scope = scopes.scope.model_copy(
                update={
                    "evidence_status": DataScopeEvidenceStatus.STALE,
                    "evidence_reason": "The qualified evidence has expired.",
                }
            )
        else:
            draft["data_scope"] = {**handoff, "fingerprint": "e" * 64}

        preflight = client.post("/api/backtests/preflight", json=draft)
        assert preflight.status_code == 200
        assert preflight.json()["valid"] is False
        issue_codes = {issue["code"] for issue in preflight.json()["issues"]}
        assert "data_scope_mismatch" in issue_codes
        if blocker == "stale":
            assert "data_scope_stale" in issue_codes
        else:
            assert "data_scope_stale" not in issue_codes
        assert coverage.calls == []

        rejected = client.post("/api/backtests/definitions", json=draft)
        assert rejected.status_code == 422
        assert {issue["code"] for issue in rejected.json()["issues"]} >= {"data_scope_mismatch"}
        assert definitions.revision is None
