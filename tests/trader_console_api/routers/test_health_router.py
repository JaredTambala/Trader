"""Contracts for the Console health HTTP router.

Subject: HTTP translation of health-service responses.
Level: In-process transport unit contract.
Collaborators: Real FastAPI router with a recording service stub; no application lifespan or database.
Guarantees: Router status codes, bodies, and cache headers follow service results without orchestration.
Non-goals: Database-schema assessment, SQL transactions, pool lifecycle, and deployment authentication.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from trader_console_api.contracts import LivenessResponse, ReadinessResponse
from trader_console_api.routers import health_router


class _HealthService:
    def __init__(self, readiness: ReadinessResponse) -> None:
        self._readiness = readiness
        self.liveness_calls = 0
        self.readiness_calls = 0

    def liveness(self) -> LivenessResponse:
        self.liveness_calls += 1
        return LivenessResponse()

    async def readiness(self) -> ReadinessResponse:
        self.readiness_calls += 1
        return self._readiness


def _client(service: _HealthService) -> TestClient:
    app = FastAPI()
    app.state.health_service = service
    app.include_router(health_router)
    return TestClient(app)


def test_live_route_delegates_to_service_and_sets_no_store() -> None:
    """Translate service liveness without acquiring or inspecting a database collaborator."""
    service = _HealthService(
        ReadinessResponse(status="ready", scope_id="paper-primary", contract_version=1)
    )

    response = _client(service).get("/health/live")

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert service.liveness_calls == 1
    assert service.readiness_calls == 0


def test_ready_route_translates_unavailable_service_result_to_503() -> None:
    """Map a service failure contract to HTTP without reinterpreting its issue evidence."""
    service = _HealthService(
        ReadinessResponse(
            status="unavailable",
            scope_id="paper-primary",
            issues=("database_unavailable",),
        )
    )

    response = _client(service).get("/health/ready")

    assert response.status_code == 503
    assert response.json()["issues"] == ["database_unavailable"]
    assert response.headers["cache-control"] == "no-store"
    assert service.readiness_calls == 1
