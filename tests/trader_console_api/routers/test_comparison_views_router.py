"""Subject: HTTP transport for saved comparison-view definitions.

Level: In-process FastAPI router contract.
Collaborators: Real router and TestClient with an application-service double.
Guarantees: Request routing, no-store responses, and stable service error mapping.
Non-goals: SQL behavior, database installation, and browser rendering.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

from trader_console_api.comparison_contracts import (
    ComparisonEvaluation,
    ComparisonViewDefinition,
    ComparisonViewDetail,
    ComparisonViewsResponse,
    SavedComparisonView,
)
from trader_console_api.routers.comparison_views import router
from trader_console_api.services.comparison_views import (
    ComparisonNotFound,
    InvalidComparisonSelection,
)


def _detail() -> ComparisonViewDetail:
    """Return one representative service response."""
    now = datetime.now(UTC)
    return ComparisonViewDetail(
        view=SavedComparisonView(
            view_id=uuid4(),
            scope_id="test-scope",
            experiment_id="experiment-1",
            definition=ComparisonViewDefinition(name="saved"),
            revision=1,
            created_at=now,
            updated_at=now,
        ),
        evaluation=ComparisonEvaluation(state="empty", eligible_run_ids=(), runs=()),
    )


class _Service:
    """Application-service double used to isolate transport behavior."""

    async def preview(self, experiment_id: str, definition: ComparisonViewDefinition) -> ComparisonEvaluation:
        """Return an empty draft evaluation."""
        return ComparisonEvaluation(state="empty", eligible_run_ids=(), runs=())

    async def list(self, experiment_id: str, *, limit: int, offset: int) -> ComparisonViewsResponse:
        """Return an empty bounded collection."""
        from trader_console_api.contracts import PageInfo

        return ComparisonViewsResponse(
            items=(), page=PageInfo(limit=limit, offset=offset, total=0, has_more=False)
        )

    async def save(self, experiment_id: str, definition: ComparisonViewDefinition):
        """Return one saved detail."""
        return _detail()

    async def get(self, experiment_id: str, view_id):
        """Return one saved detail."""
        return _detail()

    async def replace(self, experiment_id: str, view_id, update):
        """Return one replaced detail."""
        return _detail()


def _client(service: object) -> TestClient:
    """Mount the router with a service double and no lifespan."""
    app = FastAPI()
    app.include_router(router)
    app.state.comparison_view_service = service
    return TestClient(app)


def test_preview_and_create_return_no_store_and_contract_shapes() -> None:
    """Draft and save endpoints expose the typed response and cache policy."""
    client = _client(_Service())
    payload = {"name": "saved"}

    preview = client.post("/api/experiments/experiment-1/comparison-views/preview", json=payload)
    created = client.post("/api/experiments/experiment-1/comparison-views", json=payload)

    assert preview.status_code == 200
    assert preview.json()["state"] == "empty"
    assert created.status_code == 201
    assert created.json()["view"]["definition"]["name"] == "saved"
    assert created.headers["cache-control"] == "no-store"


def test_service_selection_errors_use_stable_error_envelopes() -> None:
    """Router maps domain failures without exposing repository internals."""
    class FailingService(_Service):
        async def save(self, experiment_id: str, definition: ComparisonViewDefinition):
            raise InvalidComparisonSelection("Runs are not in this experiment: run-x")

        async def get(self, experiment_id: str, view_id):
            raise ComparisonNotFound("Comparison view not found")

    client = _client(FailingService())
    payload = {"name": "saved"}

    invalid = client.post("/api/experiments/experiment-1/comparison-views", json=payload)
    missing = client.get(f"/api/experiments/experiment-1/comparison-views/{uuid4()}")

    assert invalid.status_code == 422
    assert invalid.json()["code"] == "invalid_comparison_selection"
    assert missing.status_code == 404
    assert missing.json()["code"] == "comparison_view_not_found"
