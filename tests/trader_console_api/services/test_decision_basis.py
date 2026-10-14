"""Persisted decision evidence discovery at the Console service boundary.

Subject: Exact canonical references and fail-closed human action availability.
Level: Service unit tests.
Collaborators: Repository double, real transport and research domain contracts.
Guarantees: No invented refs, ambiguous outcomes, stale evidence or agent actions.
Non-goals: SQL storage, scientific qualification and frontend rendering.
"""

import asyncio
from contextlib import asynccontextmanager
from copy import deepcopy

import pytest

from trader_console_api.contracts import TraderPrincipal
from trader_console_api.repositories.decision_basis import pinned_reference
from trader_console_api.repositories.next_research_decisions import NextResearchDecisionEvidenceUnavailable
from trader_console_api.services.decision_basis import DecisionBasisService
from trader_console_api.services.next_research_decisions import NextDecisionAuthorityError


def _record(kind, identity, payload=None, **extra):
    """Create bounded canonical records with the actual artifact owners."""
    owner = {"dataset_manifest": "Data", "workflow_outcome": "Orchestration", "research_session": "Orchestration"}.get(kind, "Review" if "report" in kind else "Experiments")
    return {"artifact_type": kind, "artifact_id": identity, "domain_owner": owner,
            "payload": payload or {}, "metadata": {}, **extra}


class Session:
    """Model canonical record reads and the separate command evidence validator."""

    def __init__(self, *, blocked=True):
        self.records = {}
        self.validated = None
        self.failure = None
        self.terminal = []
        self.linked_rows = {}
        run = _record("backtest_run", "run-1", {"run_id": "run-1"})
        data = _record("dataset_manifest", "data-1", {"scope_fingerprint": "scope-1"})
        implementation = _record("implementation_version", "strategy-1")
        protocol = _record("experiment_protocol", "protocol-1", {
            "datasets": [{"dataset_manifest_ref": pinned_reference(data)}],
            "strategy": {"implementation_ref": pinned_reference(implementation)},
            "risk_managers": [], "material_assumptions": [], "costs": [],
        })
        review = _record("evaluation_report", "review-1", {"run_id": "run-1"}, status="negative")
        outcome = _record("workflow_outcome", "outcome-1", {
            "produced_artifact_refs": [pinned_reference(run)],
            "protocol_ref": pinned_reference(protocol), "status": "blocked" if blocked else "completed",
            "review_verdict_refs": [] if blocked else [pinned_reference(review)],
            "blockers": [{"code": "evaluation_unavailable", "message": "Independent review is unavailable", "details": {}}],
        })
        for row in (run, data, implementation, protocol, review, outcome):
            self.records[(row["artifact_type"], row["artifact_id"])] = row
        self.terminal = [outcome]

    async def require_storage(self):
        """Declare test storage available."""

    async def artifact(self, kind, identity):
        """Resolve exactly one requested key."""
        return self.records.get((kind, identity))

    async def resolve(self, reference):
        """Resolve exact fixture references; hash validation belongs to the adapter."""
        return self.records[(reference["artifact_type"], reference["artifact_id"])]

    async def outcomes(self, run_id):
        """Return configured exact terminal matches."""
        assert run_id == "run-1"
        return self.terminal

    async def linked(self, run_id, kinds):
        """Return only the explicit run-linked fixture records requested."""
        return [row for row in self.linked_rows.values() if row["artifact_type"] in kinds]

    async def validate_evidence(self, decision, *, run_id):
        """Capture the immutable candidate or report canonical evidence drift."""
        if self.failure:
            raise NextResearchDecisionEvidenceUnavailable(self.failure)
        self.validated = decision


class Repository:
    def __init__(self, session):
        self.value = session

    @asynccontextmanager
    async def session(self):
        """Offer a read-only resolver with no command/write method."""
        yield self.value


def _get(session, principal="human:jared"):
    """Call the real service with a known authenticated principal."""
    return asyncio.run(DecisionBasisService(Repository(session)).get("run-1", TraderPrincipal(principal_id=principal)))


def test_blocked_evidence_has_exact_hashes_and_only_reject_refine():
    """Absent scientific reviews remain unassessed with permitted human actions."""
    session = Session()
    result = _get(session)
    assert result.status == "available"
    assert result.permitted_outcomes == ("reject", "refine")
    assert result.evidence.blocked_evidence.scientific_review_status == "not_assessed"
    assert result.evidence.review_refs == ()
    assert result.evidence.blocked_evidence.session_ref is None
    assert result.evidence.source_run_ref.metadata["payload_sha256"]
    assert session.validated.source_run_ref.artifact_id == "run-1"


def test_genuine_negative_review_remains_inspectable_and_actionable():
    """A negative review remains real evidence rather than an absent assessment."""
    result = _get(Session(blocked=False))
    assert result.status == "available"
    assert result.evidence.blocked_evidence is None
    assert result.evidence.review_refs[0].artifact_id == "review-1"
    assert result.permitted_outcomes == ("reject", "refine", "continue")


@pytest.mark.parametrize("missing", [True, False])
def test_missing_or_ambiguous_terminal_evidence_exposes_no_actions(missing):
    """Do not select another outcome when canonical evidence is ambiguous."""
    session = Session()
    session.terminal = [] if missing else [*session.terminal, deepcopy(session.terminal[0])]
    result = _get(session)
    assert result.status == ("unavailable" if missing else "incompatible")
    assert result.evidence is None and result.permitted_outcomes == ()
    assert session.validated is None


def test_canonical_hash_drift_removes_the_entire_actionable_basis():
    """A stale payload is incompatible, never an actionable cached identity."""
    session = Session()
    session.failure = "evidence payload changed: run-1"
    result = _get(session)
    assert result.status == "incompatible"
    assert result.evidence is None and result.permitted_outcomes == ()


def test_agent_cannot_inspect_human_decision_basis():
    """An agent principal is rejected before repository reads can disclose human decision evidence."""
    with pytest.raises(NextDecisionAuthorityError):
        _get(Session(), "agent:evaluation")


def test_published_reference_excludes_unrelated_producer_metadata():
    """Producer prompts and arbitrary metadata never enter the outward basis."""
    record = _record("backtest_run", "run-1", metadata={"prompt": "private", "branch_id": "b1", "revision": 2})
    reference = pinned_reference(record)
    assert "prompt" not in reference["metadata"]
    assert reference["metadata"]["branch_id"] == "b1"
    assert reference["metadata"]["revision"] == 2


def test_genuine_optimization_review_preserves_existing_supported_path():
    """Explicit run-linked optimization evidence is kept without independent claims."""
    session = Session()
    session.terminal = []
    session.linked_rows = {key: value for key, value in session.records.items() if key[0] in {"dataset_manifest", "implementation_version"}}
    review = _record("parameter_optimization_evaluation_report", "optimization-review", {"run_id": "run-1"})
    session.linked_rows[(review["artifact_type"], review["artifact_id"])] = review
    result = _get(session)
    assert result.status == "available"
    assert result.evidence.review_refs[0].artifact_type == "parameter_optimization_evaluation_report"
