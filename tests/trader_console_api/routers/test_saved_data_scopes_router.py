"""Subject: HTTP transport for saved exact Data scopes.

Level: In-process FastAPI router contract.
Collaborators: Real router/TestClient with an application-service double.
Guarantees: create, list, reopen, revalidate, error mapping, and no-store headers.
Non-goals: PostgreSQL persistence and frontend rendering.
"""

from datetime import UTC, datetime
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

from trader_console_api.data_scope_contracts import (
    DataScopeEvidenceStatus,
    DataScopePageInfo,
    DataScopeSourcePolicy,
    SavedDataScope,
    SavedDataScopeCreate,
    SavedDataScopesResponse,
)
from trader_console_api.routers.saved_data_scopes import router


def _scope() -> SavedDataScope:
    """Build one representative public saved-scope response."""
    now = datetime(2026, 1, 1, tzinfo=UTC)
    return SavedDataScope(
        saved_scope_id=uuid4(),
        scope_id="console-a",
        fingerprint="a" * 64,
        name="Research window",
        asset_class="stock",
        symbols=("AAPL",),
        timeframe="1Min",
        interval="1Min",
        start=now,
        end=datetime(2026, 1, 2, tzinfo=UTC),
        source_policy=DataScopeSourcePolicy(provider="alpaca", source="iex"),
        research_role="backtest_authoring",
        manifest_artifact_id="manifest-1",
        quality_artifact_id="quality-1",
        evidence_status=DataScopeEvidenceStatus.ACTIVE,
        created_by="operator-1",
        idempotency_key="request-1",
        created_at=now,
        updated_at=now,
    )


class _Service:
    """Application-service double isolating the HTTP contract."""

    def __init__(self) -> None:
        self.value = _scope()
        self.calls: list[str] = []

    async def create(self, request: SavedDataScopeCreate) -> SavedDataScope:
        """Return the saved scope."""
        self.calls.append("create")
        return self.value

    async def list(self, *, limit: int, offset: int) -> SavedDataScopesResponse:
        """Return one bounded collection page."""
        self.calls.append("list")
        return SavedDataScopesResponse(
            items=(self.value,),
            page=DataScopePageInfo(limit=limit, offset=offset, total=1, has_more=False),
        )

    async def get(self, saved_scope_id):
        """Return the reopened scope."""
        self.calls.append("get")
        return self.value

    async def revalidate(self, saved_scope_id):
        """Return the current qualification state."""
        self.calls.append("revalidate")
        return self.value


def test_saved_scope_routes_preserve_typed_identity_and_no_store() -> None:
    """The public routes expose exact scope fields and explicit revalidation."""
    app = FastAPI()
    app.include_router(router)
    service = _Service()
    app.state.saved_data_scope_service = service
    client = TestClient(app)
    payload = {
        "name": "Research window",
        "asset_class": "stock",
        "symbols": ["AAPL"],
        "timeframe": "1Min",
        "interval": "1Min",
        "start": "2026-01-01T00:00:00Z",
        "end": "2026-01-02T00:00:00Z",
        "source_policy": {"provider": "alpaca", "source": "iex"},
        "research_role": "backtest_authoring",
        "manifest_artifact_id": "manifest-1",
        "quality_artifact_id": "quality-1",
        "created_by": "operator-1",
        "idempotency_key": "request-1",
    }

    created = client.post("/api/data-scopes", json=payload)
    listed = client.get("/api/data-scopes")
    loaded = client.get(f"/api/data-scopes/{service.value.saved_scope_id}")
    revalidated = client.post(f"/api/data-scopes/{service.value.saved_scope_id}/revalidate")

    assert created.status_code == 201
    assert listed.status_code == 200
    assert loaded.status_code == 200
    assert revalidated.status_code == 200
    assert loaded.json()["manifest_artifact_id"] == "manifest-1"
    assert loaded.json()["quality_artifact_id"] == "quality-1"
    assert loaded.headers["cache-control"] == "no-store"
    assert service.calls == ["create", "list", "get", "revalidate"]
