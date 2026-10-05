"""HTTP contracts for the authorized paper operator command boundary.

Subject: Authentication, typed command submission, and stable HTTP errors.
Level: In-process FastAPI transport.
Collaborators: Service double and authentication provider double; no database or broker.
Guarantees: Missing authentication fails closed and authorized requests return durable receipts.
Non-goals: Repository SQL, admission projection validation, and browser layout.
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from trader_console_api.contracts import PaperOperatorCommandRecord, TraderPrincipal
from trader_console_api.routers.paper_operator_commands import (
    get_paper_operator_command_service,
    router,
)


def _record() -> PaperOperatorCommandRecord:
    return PaperOperatorCommandRecord(
        command_id=str(uuid4()),
        scope_id="paper-primary",
        command="set_halt",
        admission_id="admission-1",
        idempotency_key="key-1",
        requested_by="human:operator",
        status="requested",
        requested_at=datetime.now(timezone.utc),
    )


class _Service:
    async def submit(self, request, principal):
        assert request.command == "set_halt"
        assert principal.principal_id == "human:operator"
        return _record()


class _Provider:
    async def authenticate(self, _request: Request) -> TraderPrincipal:
        return TraderPrincipal(principal_id="human:operator")


def test_command_route_requires_authentication() -> None:
    """Do not expose a mutation route when no provider is configured."""
    app = FastAPI()
    app.state.authentication_provider = None
    app.state.paper_operator_command_service = _Service()
    app.include_router(router)
    response = TestClient(app).post(
        "/api/paper/commands",
        json={"command": "set_halt", "admission_id": "admission-1", "idempotency_key": "key-1"},
    )
    assert response.status_code == 401


def test_authenticated_command_returns_audited_receipt() -> None:
    """Bind the request to the injected human principal and expose no-store evidence."""
    app = FastAPI()
    app.state.authentication_provider = _Provider()
    app.dependency_overrides[get_paper_operator_command_service] = lambda: _Service()
    app.include_router(router)
    response = TestClient(app).post(
        "/api/paper/commands",
        json={"command": "set_halt", "admission_id": "admission-1", "idempotency_key": "key-1"},
    )
    assert response.status_code == 202
    assert response.headers["cache-control"] == "no-store"
    assert response.json()["requested_by"] == "human:operator"
