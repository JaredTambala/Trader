"""HTTP boundary contracts for human next-decision command/read paths.

Subject: Authentication, typed command routing, and fail-closed blocker mapping.
Level: In-process FastAPI transport.
Collaborators: Service/provider doubles; no database, artifact store, or browser.
Guarantees: Missing authentication fails closed and exact typed records are returned.
Non-goals: Evidence SQL, revision persistence, statistical review, and UI layout.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from trader_console_api.contracts import (
    NextDecisionArtifactReference,
    NextResearchDecisionRecord,
    NextResearchDecisionsResponse,
    PageInfo,
    TraderPrincipal,
)
from trader_console_api.routers.next_research_decisions import (
    get_next_research_decision_service,
    router,
)


def _ref(artifact_id: str, artifact_type: str, owner: str) -> NextDecisionArtifactReference:
    """Build a response reference fixture."""
    return NextDecisionArtifactReference(
        artifact_id=artifact_id,
        artifact_type=artifact_type,
        domain_owner=owner,
        uri=f"research://postgres/{artifact_type}/{artifact_id}",
    )


def _record() -> NextResearchDecisionRecord:
    """Build one complete response record."""
    return NextResearchDecisionRecord(
        artifact_type="research_next_decision",
        artifact_id="research_next_decision_1",
        decision_id="decision-1",
        revision=1,
        outcome="reject",
        rationale="No robust edge.",
        operator="human:jared",
        decided_at=datetime(2026, 10, 5, tzinfo=timezone.utc),
        source_run_ref=_ref("run-1", "backtest_run", "Experiments"),
        data_ref=_ref("data-1", "dataset_manifest", "Data"),
        implementation_refs=(_ref("impl-1", "implementation_version", "Experiments"),),
        assumptions={},
        review_refs=(_ref("review-1", "evaluation_report", "Review"),),
        limitations=("Single holdout",),
        decision_digest="a" * 64,
    )


class _Service:
    async def create(self, run_id, request, principal):
        """Return the typed record after binding request and principal."""
        assert run_id == "run-1"
        assert principal.principal_id == "human:jared"
        assert request.decision_id == "decision-1"
        return _record()

    async def list(self, run_id, *, limit, offset, principal):
        """Return one bounded latest-revision page."""
        assert (run_id, limit, offset, principal.principal_id) == ("run-1", 20, 0, "human:jared")
        return NextResearchDecisionsResponse(
            items=(_record(),),
            page=PageInfo(limit=20, offset=0, total=1, has_more=False),
        )

    async def get(self, run_id, decision_id, principal, revision=None):
        """Return the exact record requested by the route."""
        assert (run_id, decision_id, principal.principal_id, revision) == (
            "run-1",
            "decision-1",
            "human:jared",
            None,
        )
        return _record()


class _Provider:
    async def authenticate(self, _request: Request) -> TraderPrincipal:
        """Resolve the fixture human operator."""
        return TraderPrincipal(principal_id="human:jared")


def _app(*, provider: Any = None) -> FastAPI:
    """Compose the router with injected transport doubles."""
    app = FastAPI()
    app.state.authentication_provider = provider
    app.state.next_research_decision_service = _Service()
    app.dependency_overrides[get_next_research_decision_service] = lambda: _Service()
    app.include_router(router)
    return app


def _payload() -> dict[str, object]:
    """Build one valid reject command payload."""
    return {
        "decision_id": "decision-1",
        "outcome": "reject",
        "rationale": "No robust edge.",
        "source_run_ref": _ref("run-1", "backtest_run", "Experiments").model_dump(),
        "data_ref": _ref("data-1", "dataset_manifest", "Data").model_dump(),
        "implementation_refs": [_ref("impl-1", "implementation_version", "Experiments").model_dump()],
        "review_refs": [_ref("review-1", "evaluation_report", "Review").model_dump()],
        "limitations": ["Single holdout"],
    }


def test_mutation_requires_authentication() -> None:
    """Do not expose the human decision command without an auth provider."""
    response = TestClient(_app()).post("/api/runs/run-1/next-decisions", json=_payload())
    assert response.status_code == 401


def test_authenticated_command_and_read_paths_return_typed_evidence() -> None:
    """Record, list, and reopen a decision through the public API routes."""
    client = TestClient(_app(provider=_Provider()))
    created = client.post("/api/runs/run-1/next-decisions", json=_payload())
    assert created.status_code == 201
    assert created.json()["artifact_type"] == "research_next_decision"
    listed = client.get("/api/runs/run-1/next-decisions")
    assert listed.status_code == 200
    assert listed.json()["items"][0]["decision_id"] == "decision-1"
    reopened = client.get("/api/runs/run-1/next-decisions/decision-1")
    assert reopened.status_code == 200
    assert reopened.json()["source_run_ref"]["artifact_id"] == "run-1"

