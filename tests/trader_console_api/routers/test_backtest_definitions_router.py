"""HTTP transport contracts for immutable Console backtest definitions.

Subject: Definition CRUD/revision routing, cache policy, and stable error mapping.
Level: In-process FastAPI router contract.
Collaborators: Real router/TestClient with an application-service double.
Guarantees: Valid requests route to the right service operation and preflight failures remain typed 422 responses.
Non-goals: PostgreSQL persistence, installer behavior, and frontend rendering.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

from trader_console_api.contracts import (
    BacktestDefinitionRevision,
    BacktestDefinitionsResponse,
    BacktestPreflightResponse,
    PageInfo,
)
from trader_console_api.data_scope_contracts import BacktestDataScopeHandoff, DataScopeEvidenceStatus, DataScopeSourcePolicy
from trader_console_api.routers.backtest_definitions import router
from trader_console_api.services.backtest_definitions import InvalidBacktestDefinition


class _Service:
    """Application-service double isolating HTTP behavior."""

    def __init__(self, revision: BacktestDefinitionRevision) -> None:
        self.revision = revision
        self.calls: list[str] = []

    async def create(self, draft):
        """Return one stored first revision."""
        self.calls.append("create")
        return self.revision

    async def create_revision(self, definition_id, draft):
        """Return one appended revision."""
        self.calls.append("create_revision")
        return self.revision.model_copy(update={"revision": 2, "definition_id": str(definition_id)})

    async def get(self, definition_id):
        """Return the latest revision."""
        self.calls.append("get")
        return self.revision

    async def list(self, *, limit, offset):
        """Return one bounded page."""
        self.calls.append("list")
        return BacktestDefinitionsResponse(
            items=(self.revision,),
            page=PageInfo(limit=limit, offset=offset, total=1, has_more=False),
        )


def _client(service: object) -> TestClient:
    """Mount the router without application lifespan."""
    app = FastAPI()
    app.include_router(router)
    app.state.backtest_definition_service = service
    return TestClient(app)


def _revision() -> BacktestDefinitionRevision:
    """Build one representative persisted revision response."""
    from trader_console_api.contracts import BacktestDefinition

    definition = BacktestDefinition(
        display_name="Smoke",
        strategy_profile_id="noop",
        strategy_catalogue_version="standard-1",
        risk_profile_id="noop",
        risk_catalogue_version="standard-1",
        asset_class="stock",
        symbols=("AAPL",),
        timeframe="1Min",
        start=datetime(2026, 1, 1, tzinfo=UTC),
        end=datetime(2026, 1, 1, 1, tzinfo=UTC),
        initial_cash=100_000,
        data_scope=BacktestDataScopeHandoff(
            saved_scope_id=uuid4(), fingerprint="a" * 64, asset_class="stock",
            symbols=("AAPL",), timeframe="1Min", interval="1Min",
            start=datetime(2026, 1, 1, tzinfo=UTC), end=datetime(2026, 1, 1, 1, tzinfo=UTC),
            source_policy=DataScopeSourcePolicy(provider="fixture", source="fixture"),
            manifest_artifact_id="manifest-1", quality_artifact_id="quality-1",
            evidence_status=DataScopeEvidenceStatus.ACTIVE,
        ),
    )
    now = datetime(2026, 1, 1, tzinfo=UTC)
    return BacktestDefinitionRevision(
        definition_id=str(uuid4()),
        scope_id="scope-a",
        revision=1,
        fingerprint="a" * 64,
        definition=definition,
        created_at=now,
        updated_at=now,
    )


def _payload() -> dict[str, object]:
    """Return a valid draft payload accepted by the transport model."""
    return {
        "strategy_profile_id": "noop",
        "asset_class": "stock",
        "symbols": ["AAPL"],
        "timeframe": "1Min",
        "start": "2026-01-01T00:00:00Z",
        "end": "2026-01-01T01:00:00Z",
        "data_scope": {
            "saved_scope_id": str(uuid4()), "fingerprint": "a" * 64,
            "asset_class": "stock", "symbols": ["AAPL"], "universe": None,
            "timeframe": "1Min", "interval": "1Min",
            "start": "2026-01-01T00:00:00Z", "end": "2026-01-01T01:00:00Z",
            "source_policy": {"provider": "fixture", "source": "fixture", "allow_fallback": False},
            "manifest_artifact_id": "manifest-1", "quality_artifact_id": "quality-1",
            "evidence_status": "active", "evidence_reason": None,
        },
    }


def test_definition_routes_return_revision_and_no_store() -> None:
    """Create/list/get/revision routes expose generated response shapes and cache policy."""
    service = _Service(_revision())
    client = _client(service)
    definition_id = service.revision.definition_id

    created = client.post("/api/backtests/definitions", json=_payload())
    listed = client.get("/api/backtests/definitions")
    loaded = client.get(f"/api/backtests/definitions/{definition_id}")
    revised = client.post(f"/api/backtests/definitions/{definition_id}/revisions", json=_payload())

    assert created.status_code == 201
    assert listed.status_code == 200
    assert loaded.status_code == 200
    assert revised.status_code == 201
    assert revised.json()["revision"] == 2
    assert created.headers["cache-control"] == "no-store"
    assert service.calls == ["create", "list", "get", "create_revision"]


def test_invalid_preflight_is_returned_as_typed_422() -> None:
    """Definition persistence rejects invalid drafts before any write response is emitted."""
    result = BacktestPreflightResponse(
        valid=False,
        catalogue_version="standard-1",
        issues=(
            {"severity": "error", "code": "invalid_window", "path": "end", "message": "bad"},
        ),
    )

    class _Failing(_Service):
        async def create(self, draft):
            raise InvalidBacktestDefinition(result)

    response = _client(_Failing(_revision())).post("/api/backtests/definitions", json=_payload())

    assert response.status_code == 422
    assert response.json()["issues"][0]["code"] == "invalid_window"
