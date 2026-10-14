"""Human next decisions against canonical blocked terminal evidence.

Subject: Exact blocked outcome, protocol and run lineage without dummy reviews.
Level: In-process domain contract with real in-memory canonical artifacts.
Collaborators: Artifact store and typed workflow outcomes; no model or broker.
Guarantees: Human authority, immutable replay, complete blockers and fail-closed
canonical identity checks including valid but unrelated data/implementations.
Non-goals: HTTP, database durability, independent scientific review or execution.
"""
from dataclasses import replace

import pytest

from trader_research.governance import (
    BoundedNextExperiment, NextDecisionOutcome,
    NextResearchDecision, create_next_research_decision,
)
from trader_research.governance.handoffs import ResearchIssue


from tests.trader_research.governance.support.blocked_decisions import blocked_fixture

def record(store, decision, actor="human:jared"):
    """Submit the exact decision through the human-owned governance service."""
    return create_next_research_decision(decision.to_dict(), artifact_store=store, requested_by=actor, actor=actor)


def test_blocked_reject_replay_and_bounded_revision_preserve_unassessed_evidence():
    """Human reject/refine records preserve blockers and do not fabricate reviews."""
    store, first, _ = blocked_fixture()
    assert record(store, first).ok
    assert record(store, first).ok
    successor = BoundedNextExperiment(
        question="Can independent review resolve the limitation?", data_ref=first.data_ref,
        implementation_refs=first.implementation_refs, assumptions={},
        evaluation_start="2026-01-01T00:00:00Z", evaluation_end="2026-02-01T00:00:00Z",
        max_runs=1, success_criteria=("Obtain independent review",),
    )
    second = replace(first, revision=2, supersedes_artifact_id=first.artifact_id,
                     outcome=NextDecisionOutcome.REFINE, next_experiment=successor)
    assert record(store, second).ok
    recovered = NextResearchDecision.from_dict(store.load_artifact("research_next_decision", second.artifact_id))
    assert recovered.to_dict() == second.to_dict()
    assert recovered.review_refs == ()
    assert recovered.blocked_evidence.scientific_review_status == "not_assessed"
    assert len(store.list_artifacts(artifact_type="research_next_decision")) == 2


@pytest.mark.parametrize("kind", ["dataset_manifest", "implementation_version"])
def test_valid_but_unrelated_canonical_artifact_cannot_replace_protocol_evidence(kind):
    """A genuine canonical hash alone cannot attach another input to this run."""
    store, decision, save = blocked_fixture()
    other = save(kind, "unrelated", {"dataset_id": "unrelated", "implementation_version_id": "unrelated"})
    changed = replace(decision, data_ref=other) if kind == "dataset_manifest" else replace(decision, implementation_refs=(other, decision.implementation_refs[1]))
    result = record(store, changed)
    assert not result.ok
    assert not store.list_artifacts(artifact_type="research_next_decision")


@pytest.mark.parametrize("artifact", ["run", "data", "implementation", "outcome", "quality"])
def test_payload_drift_fails_even_when_identity_is_unchanged(artifact):
    """Every input and blocker-producing terminal record remains hash pinned."""
    store, decision, _ = blocked_fixture()
    refs = {"run": decision.source_run_ref, "data": decision.data_ref,
            "implementation": decision.implementation_refs[0], "outcome": decision.blocked_evidence.outcome_ref}
    kind, identity = (refs[artifact].artifact_type, refs[artifact].artifact_id) if artifact != "quality" else ("data_quality_report", "quality-1")
    original = store.load_artifact_record(kind, identity)
    store.save_artifact(artifact_type=kind, artifact_id=identity, domain_owner=original.domain_owner,
                        producer_tool=original.producer_tool, payload={**original.payload, "changed": True}, status=original.status)
    assert not record(store, decision).ok


def test_altered_blockers_and_agent_authority_fail_closed():
    """Neither changed blocker details nor an agent principal can write a choice."""
    store, decision, _ = blocked_fixture()
    changed_basis = replace(decision.blocked_evidence, blockers=(ResearchIssue("review_producer_unavailable", "Independent review is unavailable", {"role": "robustness"}),))
    assert not record(store, replace(decision, blocked_evidence=changed_basis)).ok
    assert not record(store, replace(decision, operator="agent:research"), "agent:research").ok
    assert not store.list_artifacts(artifact_type="research_next_decision")


def test_blocked_basis_rejects_missing_hash_dummy_review_and_unbounded_continue():
    """The typed boundary rejects invented reviews and successor authority."""
    _, decision, save = blocked_fixture()
    with pytest.raises(ValueError, match="payload_sha256"):
        replace(decision, data_ref=replace(decision.data_ref, metadata={}))
    with pytest.raises(ValueError, match="cannot claim"):
        replace(decision, review_refs=(save("evaluation_report", "dummy", {}),))
    with pytest.raises(ValueError, match="require next_experiment"):
        replace(decision, outcome=NextDecisionOutcome.CONTINUE)
    with pytest.raises(ValueError, match="not_assessed"):
        replace(decision.blocked_evidence, scientific_review_status="passed")


@pytest.mark.parametrize("kind", ["dataset_manifest", "implementation_version"])
def test_pinned_stale_successor_evidence_does_not_authorize_continuation(kind):
    """A valid hash does not turn stale successor inputs into admissible evidence."""
    store, decision, save = blocked_fixture()
    stale = save(kind, "stale-successor", {"dataset_id": "stale-successor"}, status="stale")
    successor = BoundedNextExperiment(
        question="A bounded follow-up", data_ref=stale if kind == "dataset_manifest" else decision.data_ref,
        implementation_refs=(stale,) if kind == "implementation_version" else decision.implementation_refs,
        assumptions={}, evaluation_start="2026-01-01T00:00:00Z", evaluation_end="2026-02-01T00:00:00Z",
        max_runs=1, success_criteria=("Resolve missing review",),
    )
    result = record(store, replace(decision, outcome=NextDecisionOutcome.CONTINUE, next_experiment=successor))
    assert not result.ok
    assert "successor evidence is not actionable" in result.errors[0]["message"]


def test_explicit_session_link_is_required_exact_and_digest_validated():
    """Only the session explicitly linked by the canonical outcome may be cited."""
    from trader_research.governance import AgentBudget, ResearchSession

    store, decision, save = blocked_fixture()
    session = ResearchSession(
        session_id="session-1", objective="Review bounded evidence", success_definition="Preserve blockers",
        operator_id="human:jared", approval_policy={}, scope_envelope={}, implementation_specification={"kind": "bounded-fixture"},
        implementation_ref=None, python_quality_guide="docs/python_code_quality.md", model_profile_id="model-1",
        agent_program_ids=("coordinator",), tool_catalog_id="tools-1", budget=AgentBudget(1, 1, 100, 60, 1, 1, 1),
    )
    session_ref = save("research_session", "session-1", session.to_dict())
    terminal = store.load_artifact_record("workflow_outcome", "outcome-1")
    save("workflow_outcome", "outcome-1", dict(terminal.payload), "blocked", {"session_id": "session-1"})
    assert not record(store, decision).ok
    linked = replace(decision, blocked_evidence=replace(decision.blocked_evidence, session_ref=session_ref))
    assert record(store, linked).ok
    unrelated = save("research_session", "session-2", replace(session, session_id="session-2").to_dict())
    assert not record(store, replace(linked, blocked_evidence=replace(linked.blocked_evidence, session_ref=unrelated))).ok


@pytest.mark.parametrize("kind,identity", [
    ("data_load_evidence", "data-1"),
    ("strategy_specification", "strategy-1"),
    ("risk_stack_specification", "risk-1"),
])
def test_same_id_different_artifact_type_cannot_replace_canonical_input(kind, identity):
    """A matching ID and valid hash cannot substitute a different artifact type."""
    store, decision, save = blocked_fixture()
    impostor = save(kind, identity, {"dataset_id": "data-1", "implementation_version_id": identity})
    if kind == "data_load_evidence":
        changed = replace(decision, data_ref=impostor)
    else:
        changed = replace(decision, implementation_refs=tuple(
            impostor if ref.artifact_id == identity else ref for ref in decision.implementation_refs
        ))
    result = record(store, changed)
    assert not result.ok
    assert not store.list_artifacts(artifact_type="research_next_decision")
