"""Application service contracts for human next-decision commands.

Subject: Human authority, exact reviewed-run binding, and append-only revision checks.
Level: In-process application service.
Collaborators: Repository session double; no SQL, HTTP, MCP, or browser.
Guarantees: Agents are rejected, route/run identity is checked, and accepted decisions are typed.
Non-goals: Canonical artifact SQL, statistical review, and UI behavior.
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

import pytest

from typing import Any

from trader_console_api.contracts import (
    NextDecisionArtifactReference,
    NextResearchDecisionRequest,
    TraderPrincipal,
)
from trader_console_api.services.next_research_decisions import (
    NextDecisionAuthorityError,
    NextDecisionRevisionConflict,
    NextResearchDecisionService,
)
from trader_console_api.repositories.next_research_decisions import NextResearchDecisionEvidenceUnavailable



_OWNERS = {
    "backtest_run": "Experiments",
    "dataset_manifest": "Data",
    "implementation_version": "Experiments",
    "evaluation_report": "Review",
}


def _ref(artifact_id: str, artifact_type: str) -> NextDecisionArtifactReference:
    """Build a canonical reference with its registered owner."""
    return NextDecisionArtifactReference(
        artifact_id=artifact_id,
        artifact_type=artifact_type,
        domain_owner=_OWNERS[artifact_type],
        uri=f"research://postgres/{artifact_type}/{artifact_id}",
        metadata={"payload_sha256": "a" * 64},
    )


def decision_request(**overrides: Any) -> NextResearchDecisionRequest:
    """Build one complete first-revision request."""
    values: dict[str, Any] = {
        "decision_id": "decision-1",
        "outcome": "reject",
        "rationale": "No robust edge.",
        "source_run_ref": _ref("run-1", "backtest_run"),
        "data_ref": _ref("data-1", "dataset_manifest"),
        "implementation_refs": (_ref("impl-1", "implementation_version"),),
        "review_refs": (_ref("review-1", "evaluation_report"),),
        "limitations": ("Single holdout",),
    }
    values.update(overrides)
    return NextResearchDecisionRequest.model_validate(values)


class _Session:
    def __init__(self, latest_value: tuple[int, str] | None = None, existing=None) -> None:
        self.latest_value = latest_value
        self.existing = existing
        self.validated = False
        self.created = None

    async def require_storage(self) -> None:
        """Storage is available in the service fixture."""

    async def validate_evidence(self, decision, *, run_id: str) -> None:
        """Capture the exact run binding sent to the repository."""
        self.validated = run_id == "run-1"

    async def latest(self, _decision_id: str):
        """Return configured revision lineage."""
        return self.latest_value

    async def create(self, decision, *, requested_by: str):
        """Capture and return the immutable domain decision."""
        self.created = (decision, requested_by)
        return decision

    async def get(self, _run_id: str, _decision_id: str, _revision: int | None = None):
        """No stored decision is needed for the first-revision fixture."""
        return self.existing


class _Repository:
    scope_id = "backtest-primary"

    def __init__(self, latest_value: tuple[int, str] | None = None, existing=None) -> None:
        self.session_value = _Session(latest_value, existing)

    @asynccontextmanager
    async def session(self, *, write: bool = False):
        """Yield the configured repository session."""
        assert write
        yield self.session_value


def test_human_can_record_first_revision_with_exact_run_binding() -> None:
    """The service passes human identity and reviewed-run identity into persistence."""
    repository = _Repository()
    service = NextResearchDecisionService(repository)
    result = asyncio.run(
        service.create(
            "run-1",
            decision_request(),
            TraderPrincipal(principal_id="human:jared"),
        )
    )
    assert result.outcome == "reject"
    assert result.operator == "human:jared"
    assert repository.session_value.validated is True
    assert repository.session_value.created is not None


def test_exact_command_replay_returns_the_existing_immutable_revision() -> None:
    """A retry with the same decision identity reopens the stored revision."""
    first_repository = _Repository()
    service = NextResearchDecisionService(first_repository)
    first = asyncio.run(
        service.create("run-1", decision_request(), TraderPrincipal(principal_id="human:jared"))
    )
    stored = first_repository.session_value.created[0]
    replay_repository = _Repository(existing=stored)
    replay = asyncio.run(
        NextResearchDecisionService(replay_repository).create(
            "run-1", decision_request(), TraderPrincipal(principal_id="human:jared")
        )
    )
    assert replay.artifact_id == first.artifact_id
    assert replay.decided_at == first.decided_at


def test_agent_and_wrong_run_are_rejected_before_persistence() -> None:
    """Agent identities and mismatched route refs cannot create a human decision."""
    repository = _Repository()
    service = NextResearchDecisionService(repository)
    with pytest.raises(NextDecisionAuthorityError):
        asyncio.run(service.create("run-1", decision_request(), TraderPrincipal(principal_id="agent:research")))
    with pytest.raises(NextResearchDecisionEvidenceUnavailable, match="reviewed run"):
        asyncio.run(service.create("run-2", decision_request(), TraderPrincipal(principal_id="human:jared")))
    assert repository.session_value.created is None


def test_revision_requires_contiguous_predecessor() -> None:
    """A later revision must point to the latest immutable artifact."""
    repository = _Repository((1, "research_next_decision_old"))
    service = NextResearchDecisionService(repository)
    request = decision_request(revision=2, supersedes_artifact_id="wrong")
    with pytest.raises(NextDecisionRevisionConflict, match="supersede"):
        asyncio.run(service.create("run-1", request, TraderPrincipal(principal_id="human:jared")))


def test_session_review_link_is_carried_into_the_canonical_decision() -> None:
    """The Console service preserves graph identity and named revisions exactly."""
    repository = _Repository()
    request = decision_request(session_review={
        "session_id": "session-1", "session_digest": "a" * 64,
        "graph_digest": "b" * 64,
        "review_node_keys": ["evaluation_report:review-1:r1"],
    })
    record = asyncio.run(
        NextResearchDecisionService(repository).create(
            "run-1", request, TraderPrincipal(principal_id="human:jared")
        )
    )
    assert record.session_review is not None
    assert record.session_review.graph_digest == "b" * 64
    assert repository.session_value.created[0].session_review.review_node_keys == (
        "evaluation_report:review-1:r1",
    )
