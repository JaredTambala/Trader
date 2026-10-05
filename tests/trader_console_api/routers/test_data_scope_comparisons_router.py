"""HTTP contract tests for saved data-scope comparison.

Subject: ``POST /api/data-scope-comparisons``.
Level: In-process FastAPI transport with a fake comparison service.
Collaborators: Pydantic request/response contracts; no database or browser.
Guarantees: The route is read-only, typed, no-store, and validates the bounded selection.
Non-goals: Compatibility calculations or producer evidence persistence.
"""

from __future__ import annotations

from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

from trader_console_api.data_scope_comparison_contracts import (
    DataScopeComparisonRequest,
    DataScopeComparisonResponse,
)
from trader_console_api.routers.data_scope_comparisons import (
    get_data_scope_comparison_service,
    router,
)


class _Service:
    """Transport double returning one typed comparison response."""

    async def compare(self, request: DataScopeComparisonRequest) -> DataScopeComparisonResponse:
        """Echo a bounded empty-pair response for route assertions."""
        return DataScopeComparisonResponse(
            state="unavailable",
            comparison_dimensions=request.comparison_dimensions,
            alternatives=(),
            pairs=(),
            comparable_pair_count=0,
            excluded_pair_count=0,
        )


def _app() -> FastAPI:
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_data_scope_comparison_service] = _Service
    return app


def test_comparison_route_returns_typed_read_model_without_mutation() -> None:
    """Accept two IDs and return a cache-disabled comparison response."""
    first, second = str(uuid4()), str(uuid4())
    response = TestClient(_app()).post(
        "/api/data-scope-comparisons",
        json={"saved_scope_ids": [first, second], "comparison_dimensions": ["source"]},
    )

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.json()["state"] == "unavailable"
    assert response.json()["comparison_dimensions"] == ["source"]


def test_comparison_route_rejects_duplicate_or_unbounded_selection() -> None:
    """Keep pairwise reads bounded and duplicate-free at the transport boundary."""
    identifier = str(uuid4())
    duplicate = TestClient(_app()).post(
        "/api/data-scope-comparisons",
        json={"saved_scope_ids": [identifier, identifier]},
    )
    assert duplicate.status_code == 422

    too_small = TestClient(_app()).post(
        "/api/data-scope-comparisons",
        json={"saved_scope_ids": [str(uuid4())]},
    )
    assert too_small.status_code == 422
