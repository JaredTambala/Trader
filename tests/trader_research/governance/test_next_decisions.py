"""Contracts for human-owned next decisions after a reviewed backtest.

Subject: Immutable reject/refine/continue decision revisions and bounded successor experiments.
Level: In-process governance service using the real artifact-store port.
Collaborators: InMemoryResearchArtifactStore and typed artifact references; no Console, MCP, or SQL.
Guarantees: Exact evidence is resolved before recording, agents cannot record decisions, and revisions append.
Non-goals: Statistical review judgment, experiment execution, deployment approval, and HTTP rendering.
"""

from __future__ import annotations

import pytest

from trader_research.foundation import InMemoryResearchArtifactStore, json_payload_hash, research_artifact_uri
from trader_research.governance import (
    BACKTEST_RUN,
    DATASET_MANIFEST,
    IMPLEMENTATION_VERSION,
    STRATEGY_SPECIFICATION,
    BoundedNextExperiment,
    NextDecisionOutcome,
    SessionReviewLink,
    build_next_research_decision,
    create_next_research_decision,
)
from trader_research.governance.artifacts import (
    DOMAIN_OWNER_BY_ARTIFACT_TYPE,
    EVALUATION_REPORT,
    EXPERIMENTS_DOMAIN_OWNER,
    REVIEW_DOMAIN_OWNER,
)
from trader_research.governance.handoffs import ArtifactReportRef


NOW = "2026-10-05T10:00:00Z"


def _ref(artifact_type: str, artifact_id: str, payload: dict[str, object]) -> ArtifactReportRef:
    """Build a reference pinned to the fixture payload identity."""
    return ArtifactReportRef(
        artifact_id=artifact_id,
        artifact_type=artifact_type,
        domain_owner=DOMAIN_OWNER_BY_ARTIFACT_TYPE[artifact_type],
        uri=research_artifact_uri(artifact_type, artifact_id),
        metadata={"payload_sha256": json_payload_hash(payload)},
    )


def _seed() -> tuple[InMemoryResearchArtifactStore, dict[str, ArtifactReportRef]]:
    """Create one complete evidence chain and typed references for it."""
    store = InMemoryResearchArtifactStore()
    payloads = {
        "run-1": {"artifact_type": BACKTEST_RUN, "run_id": "run-1", "status": "completed"},
        "data-1": {"artifact_type": DATASET_MANIFEST, "scope_fingerprint": "scope-v1"},
        "impl-1": {"artifact_type": IMPLEMENTATION_VERSION, "version": "strategy-v1"},
        "spec-1": {"artifact_type": STRATEGY_SPECIFICATION, "version": "strategy-v1"},
        "review-1": {"artifact_type": EVALUATION_REPORT, "run_id": "run-1", "status": "passed"},
    }
    kinds = {
        "run-1": BACKTEST_RUN,
        "data-1": DATASET_MANIFEST,
        "impl-1": IMPLEMENTATION_VERSION,
        "spec-1": STRATEGY_SPECIFICATION,
        "review-1": EVALUATION_REPORT,
    }
    owners = {
        BACKTEST_RUN: EXPERIMENTS_DOMAIN_OWNER,
        DATASET_MANIFEST: DOMAIN_OWNER_BY_ARTIFACT_TYPE[DATASET_MANIFEST],
        IMPLEMENTATION_VERSION: EXPERIMENTS_DOMAIN_OWNER,
        STRATEGY_SPECIFICATION: EXPERIMENTS_DOMAIN_OWNER,
        EVALUATION_REPORT: REVIEW_DOMAIN_OWNER,
    }
    refs: dict[str, ArtifactReportRef] = {}
    for artifact_id, payload in payloads.items():
        artifact_type = kinds[artifact_id]
        store.save_artifact(
            artifact_type=artifact_type,
            artifact_id=artifact_id,
            domain_owner=owners[artifact_type],
            producer_tool="fixture",
            payload=payload,
            status=str(payload.get("status") or "available"),
        )
        refs[artifact_id] = _ref(artifact_type, artifact_id, payload)
    return store, refs


def _decision(refs: dict[str, ArtifactReportRef], *, outcome: NextDecisionOutcome = NextDecisionOutcome.REJECT, **overrides: object):
    """Build one complete decision payload for the service tests."""
    values: dict[str, object] = {
        "decision_id": "decision-1",
        "revision": 1,
        "outcome": outcome,
        "rationale": "The reviewed result does not survive the stated limitations.",
        "operator": "human:jared",
        "decided_at": NOW,
        "source_run_ref": refs["run-1"],
        "data_ref": refs["data-1"],
        "implementation_refs": (refs["impl-1"], refs["spec-1"]),
        "assumptions": {"fill_model": "next_bar"},
        "review_refs": (refs["review-1"],),
        "limitations": ("Single holdout window",),
    }
    values.update(overrides)
    if outcome in {NextDecisionOutcome.REFINE, NextDecisionOutcome.CONTINUE} and "next_experiment" not in values:
        values["next_experiment"] = BoundedNextExperiment(
            question="Does the result persist under a fresh holdout?",
            data_ref=refs["data-1"],
            implementation_refs=(refs["impl-1"],),
            assumptions={"fill_model": "next_bar"},
            evaluation_start="2026-11-01T00:00:00Z",
            evaluation_end="2026-12-01T00:00:00Z",
            max_runs=3,
            success_criteria=("No material degradation",),
        )
    return build_next_research_decision(**values)


def test_human_decision_is_idempotent_and_retains_exact_evidence() -> None:
    """The same human decision can be replayed without creating a second artifact."""
    store, refs = _seed()
    decision = _decision(refs)
    payload = decision.to_dict()
    created = create_next_research_decision(
        payload, artifact_store=store, requested_by="human:jared", actor="human:jared"
    )
    replay = create_next_research_decision(
        payload, artifact_store=store, requested_by="human:jared", actor="human:jared"
    )

    assert created.ok is True
    assert replay.ok is True
    assert created.data["research_next_decision"]["data_ref"]["artifact_id"] == "data-1"
    assert len(store.list_artifacts(artifact_type="research_next_decision")) == 1


def test_refine_and_continue_require_a_bounded_successor() -> None:
    """A forward decision cannot be recorded without an explicit bounded experiment."""
    store, refs = _seed()
    decision = _decision(refs)
    missing = {**decision.to_dict(), "outcome": "refine", "next_experiment": None}
    result = create_next_research_decision(
        missing,
        artifact_store=store,
        requested_by="human:jared",
        actor="human:jared",
    )
    assert result.ok is False
    assert "require next_experiment" in result.errors[0]["message"]


def test_changed_or_missing_evidence_and_agent_authority_fail_closed() -> None:
    """Stale evidence and non-human identities cannot cross the decision gate."""
    store, refs = _seed()
    decision = _decision(refs)
    store.save_artifact(
        artifact_type=EVALUATION_REPORT,
        artifact_id="review-1",
        domain_owner=REVIEW_DOMAIN_OWNER,
        producer_tool="changed",
        payload={"artifact_type": EVALUATION_REPORT, "run_id": "run-1", "status": "changed"},
        status="blocked",
    )
    stale = create_next_research_decision(
        decision.to_dict(), artifact_store=store, requested_by="human:jared", actor="human:jared"
    )
    assert stale.ok is False
    assert "not actionable" in stale.errors[0]["message"]

    agent = create_next_research_decision(
        decision.to_dict(), artifact_store=store, requested_by="agent:research", actor="agent:research"
    )
    assert agent.ok is False
    assert "human principal" in agent.errors[0]["message"]


def test_revision_appends_without_mutating_the_original() -> None:
    """A changed human conclusion creates revision two and preserves revision one."""
    store, refs = _seed()
    first = _decision(refs)
    assert create_next_research_decision(
        first.to_dict(), artifact_store=store, requested_by="human:jared", actor="human:jared"
    ).ok
    second = _decision(
        refs,
        outcome=NextDecisionOutcome.REFINE,
        revision=2,
        supersedes_artifact_id=first.artifact_id,
        rationale="The result merits one bounded follow-up.",
    )
    result = create_next_research_decision(
        second.to_dict(), artifact_store=store, requested_by="human:jared", actor="human:jared"
    )
    assert result.ok is True
    records = store.list_artifacts(artifact_type="research_next_decision")
    assert {record.payload["revision"] for record in records} == {1, 2}
    assert store.load_artifact_record("research_next_decision", first.artifact_id).payload["outcome"] == "reject"


def test_session_review_link_pins_the_exact_graph_and_canonical_revision() -> None:
    """An agent-session decision cites the graph and refuses changed review evidence."""
    store, refs = _seed()
    review_payload = store.load_artifact_record(EVALUATION_REPORT, "review-1").payload
    store.save_artifact(
        artifact_type=EVALUATION_REPORT, artifact_id="review-1", domain_owner=REVIEW_DOMAIN_OWNER,
        producer_tool="fixture", payload=review_payload, status="passed",
        metadata={"session_id": "session-1", "revision": 1},
    )
    pinned = ArtifactReportRef(
        artifact_id=refs["review-1"].artifact_id,
        artifact_type=refs["review-1"].artifact_type,
        domain_owner=refs["review-1"].domain_owner,
        uri=refs["review-1"].uri,
        metadata={"payload_sha256": json_payload_hash(review_payload)},
    )
    link = SessionReviewLink(
        session_id="session-1", session_digest="a" * 64, graph_digest="b" * 64,
        review_node_keys=("evaluation_report:review-1:r1",),
    )
    decision = _decision(refs, review_refs=(pinned,), session_review=link)
    assert create_next_research_decision(
        decision.to_dict(), artifact_store=store, requested_by="human:jared", actor="human:jared"
    ).ok
    assert decision.to_dict()["session_review"] == link.to_dict()

    store.save_artifact(
        artifact_type=EVALUATION_REPORT, artifact_id="review-1", domain_owner=REVIEW_DOMAIN_OWNER,
        producer_tool="fixture", payload=review_payload, status="passed",
        metadata={"session_id": "session-1", "revision": 2},
    )
    stale = _decision(refs, review_refs=(pinned,), session_review=link, decision_id="decision-2")
    result = create_next_research_decision(
        stale.to_dict(), artifact_store=store, requested_by="human:jared", actor="human:jared"
    )
    assert not result.ok
    assert "identity changed" in result.errors[0]["message"]


def test_session_review_link_rejects_unpinned_and_mismatched_review_refs() -> None:
    """Graph references cannot be attached to another review artifact or unpinned evidence."""
    store, refs = _seed()
    link = SessionReviewLink(
        session_id="session-1", session_digest="a" * 64, graph_digest="b" * 64,
        review_node_keys=("evaluation_report:review-1:r1",),
    )
    unpinned = ArtifactReportRef(
        artifact_id=refs["review-1"].artifact_id,
        artifact_type=refs["review-1"].artifact_type,
        domain_owner=refs["review-1"].domain_owner,
        uri=refs["review-1"].uri,
    )
    with pytest.raises(ValueError, match="pinned hashes"):
        _decision(refs, review_refs=(unpinned,), session_review=link)
    with pytest.raises(ValueError, match="match the cited review artifacts"):
        _decision(refs, session_review=SessionReviewLink(
            session_id="session-1", session_digest="a" * 64, graph_digest="b" * 64,
            review_node_keys=("evaluation_report:other:r1",),
        ))
