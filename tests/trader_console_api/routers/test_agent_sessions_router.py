"""HTTP boundaries for the human Console agent-session workspace.

Subject: Authentication, authority, typed reads, and command routing.
Level: In-process FastAPI transport.
Collaborators: Service/provider doubles; no database, runtime, MCP, or browser.
Guarantees: Missing authentication returns 401, agent identities return 403, and
human-owned reads/commands are redacted typed responses.
Non-goals: SQL projection correctness, runtime command application, and visual layout.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from trader_console_api.contracts import (
    AgentSessionBudgetLimits,
    AgentSessionBudgetUsage,
    AgentSessionCommandRecord,
    AgentSessionCommandsResponse,
    AgentSessionProjection,
    PageInfo,
    TraderPrincipal,
)
from trader_console_api.routers.agent_sessions import get_agent_session_service, router
from trader_console_api.services.agent_sessions import AgentSessionAuthorityError


def _projection() -> AgentSessionProjection:
    """Build one complete redacted workspace response."""
    return AgentSessionProjection(
        session_id="session-1",
        session_digest="a" * 64,
        operator_id="human:jared",
        objective="Inspect a bounded question.",
        success_definition="Return evidence.",
        status="awaiting_operator",
        model_profile_id="model-v1",
        agent_program_ids=("coordinator-v1",),
        tool_catalog_id="catalogue-v1",
        scope_summary={"symbols": ["AAPL"]},
        budget_limits=AgentSessionBudgetLimits(
            max_model_calls=4,
            max_tool_calls=8,
            max_tokens=1000,
            max_duration_seconds=60,
            max_mutations=1,
            max_revisions=1,
            concurrency_limit=2,
        ),
        budget_used=AgentSessionBudgetUsage(
            model_calls=1,
            tool_calls=1,
            tokens=42,
            duration_ms=100,
            mutations=0,
            revisions=0,
        ),
    )


class _Service:
    async def get(self, session_id, principal):
        """Return a projection after observing route identity."""
        assert session_id == "session-1"
        if principal.principal_id != "human:jared":
            raise AgentSessionAuthorityError("A human operator principal is required")
        return _projection()

    async def command(self, session_id, request, principal):
        """Return one command receipt after observing authority."""
        if principal.principal_id != "human:jared":
            raise AgentSessionAuthorityError("A human operator principal is required")
        assert (session_id, request.command, principal.principal_id) == (
            "session-1",
            "interrupt",
            "human:jared",
        )
        return AgentSessionCommandRecord(
            command_id="00000000-0000-0000-0000-000000000001",
            session_id=session_id,
            command=request.command,
            idempotency_key=request.idempotency_key,
            requested_by=principal.principal_id,
            status="requested",
            requested_at=datetime(2026, 10, 5, tzinfo=timezone.utc),
        )

    async def list_commands(self, session_id, *, limit, offset, principal):
        """Return a bounded command page."""
        await self.get(session_id, principal)
        return AgentSessionCommandsResponse(
            items=(),
            page=PageInfo(limit=limit, offset=offset, total=0, has_more=False),
        )

    async def get_command(self, session_id, command_id, principal):
        """Return one command receipt after owner verification."""
        await self.get(session_id, principal)
        return AgentSessionCommandRecord(
            command_id=str(command_id),
            session_id=session_id,
            command="inspect",
            idempotency_key="intent-1",
            requested_by=principal.principal_id,
            status="requested",
            requested_at=datetime(2026, 10, 5, tzinfo=timezone.utc),
        )


class _Provider:
    def __init__(self, principal_id: str) -> None:
        self.principal_id = principal_id

    async def authenticate(self, _request: Request) -> TraderPrincipal:
        """Resolve the configured identity for the transport fixture."""
        return TraderPrincipal(principal_id=self.principal_id)


def _app(*, provider: Any = None) -> FastAPI:
    """Compose the router with authentication and service doubles."""
    app = FastAPI()
    app.state.authentication_provider = provider
    app.state.agent_session_service = _Service()
    app.dependency_overrides[get_agent_session_service] = lambda: _Service()
    app.include_router(router)
    return app


def test_session_workspace_requires_authentication() -> None:
    """No configured provider means no public session or command surface."""
    response = TestClient(_app()).get("/api/agent-sessions/session-1")
    assert response.status_code == 401


def test_agent_identity_is_rejected_and_human_can_inspect_and_interrupt() -> None:
    """Only the authenticated human owner may use the workspace controls."""
    denied = TestClient(_app(provider=_Provider("agent:coordinator"))).get(
        "/api/agent-sessions/session-1"
    )
    assert denied.status_code == 403
    denied_command = TestClient(_app(provider=_Provider("agent:coordinator"))).post(
        "/api/agent-sessions/session-1/commands",
        json={
            "command": "interrupt",
            "idempotency_key": "agent-intent-1",
            "reason": "An agent must not control a human session.",
        },
    )
    assert denied_command.status_code == 403

    client = TestClient(_app(provider=_Provider("human:jared")))
    inspected = client.get("/api/agent-sessions/session-1")
    assert inspected.status_code == 200
    assert inspected.json()["scope_summary"] == {"symbols": ["AAPL"]}
    assert "prompt" not in inspected.text

    command = client.post(
        "/api/agent-sessions/session-1/commands",
        json={
            "command": "interrupt",
            "idempotency_key": "intent-1",
            "reason": "Review evidence.",
        },
    )
    assert command.status_code == 202
    assert command.json()["requested_by"] == "human:jared"
