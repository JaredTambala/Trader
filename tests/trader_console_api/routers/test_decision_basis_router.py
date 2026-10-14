"""Authenticated HTTP read contract for the persisted decision evidence basis.

Subject: Human authority and exact read-only response routing.
Level: FastAPI transport unit tests.
Collaborators: Service double and real authentication dependency.
Guarantees: Missing authority fails closed and unavailable evidence stays explicit.
Non-goals: Canonical SQL validation, browser interaction and scientific acceptance.
"""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from trader_console_api.contracts import TraderPrincipal
from trader_console_api.decision_basis_contracts import DecisionBasisResponse
from trader_console_api.routers.decision_basis import router


class Provider:
    async def authenticate(self, _request):
        """Resolve the known human fixture identity."""
        return TraderPrincipal(principal_id="human:jared")


class Service:
    async def get(self, run_id, principal):
        """Return an explicit absence without attempting a mutation."""
        assert principal.principal_id == "human:jared"
        return DecisionBasisResponse(run_id=run_id, status="unavailable", reason="Canonical run artifact is unavailable")


def _app(authenticated):
    """Wire the actual router with an injected read service."""
    app = FastAPI()
    app.state.authentication_provider = Provider() if authenticated else None
    app.state.decision_basis_service = Service()
    app.include_router(router)
    return app


def test_basis_requires_authentication():
    """Evidence actions cannot be discovered through an unauthenticated route."""
    assert TestClient(_app(False)).get("/api/runs/run-1/decision-basis").status_code == 401


def test_unavailable_basis_remains_a_no_store_typed_read():
    """An authorized read preserves exact run identity without inventing inputs."""
    response = TestClient(_app(True)).get("/api/runs/run-1/decision-basis")
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.json()["run_id"] == "run-1"
    assert response.json()["status"] == "unavailable"
    assert response.json()["permitted_outcomes"] == []
