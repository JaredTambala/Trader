"""Contracts for public model-backed research-session evidence."""

from __future__ import annotations

from dataclasses import replace

from trader_research.foundation import (
    DATA_DOMAIN_OWNER,
    InMemoryResearchArtifactStore,
)
from trader_research.governance import (
    AgentBudget,
    AgentBudgetUsage,
    AgentDecisionStatus,
    ResearchIssue,
    ResearchSession,
    artifact_report_ref,
    build_agent_decision_receipt,
    create_agent_session,
    get_agent_decision,
    get_agent_session,
    read_canonical_artifact,
    record_agent_decision,
)
from trader_research.governance.artifacts import DATASET_MANIFEST


def test_session_creation_is_strict_idempotent_and_conflict_safe() -> None:
    store = InMemoryResearchArtifactStore()
    session = _session()

    first = create_agent_session(session.to_dict(), artifact_store=store)
    replay = create_agent_session(session.to_dict(), artifact_store=store)
    conflicting = create_agent_session(
        replace(session, objective="A conflicting objective.").to_dict(),
        artifact_store=store,
    )
    resolved = get_agent_session(session.session_id, artifact_store=store)

    assert first.ok is True
    assert replay.artifacts == first.artifacts
    assert conflicting.ok is False
    assert conflicting.errors[0]["code"] == "agent_session_creation_failed"
    assert resolved.data["research_session"]["session_digest"] == session.session_digest


def test_decision_receipts_verify_evidence_sequence_and_budget() -> None:
    store = InMemoryResearchArtifactStore()
    session = _session()
    create_agent_session(session.to_dict(), artifact_store=store)
    store.save_artifact(
        artifact_type=DATASET_MANIFEST,
        artifact_id="dataset_demo",
        domain_owner=DATA_DOMAIN_OWNER,
        producer_tool="data_create_research_snapshot",
        payload={"artifact_type": DATASET_MANIFEST, "dataset_id": "dataset_demo"},
        status="complete",
    )
    evidence = artifact_report_ref(DATASET_MANIFEST, "dataset_demo")
    first = build_agent_decision_receipt(
        session_id=session.session_id,
        branch_id="branch-main",
        sequence=1,
        actor="Research Coordinator",
        program_id="coordinator-v1",
        model_profile_id=session.model_profile_id,
        action="delegate",
        status=AgentDecisionStatus.ACCEPTED,
        summary="Delegate independent Data and Strategy investigations.",
        evidence_refs=(evidence,),
        budget_used=AgentBudgetUsage(model_calls=1, tokens=80),
        next_actions=("await_specialists",),
    )
    second = build_agent_decision_receipt(
        session_id=session.session_id,
        branch_id="branch-main",
        sequence=2,
        actor="Research Coordinator",
        program_id="coordinator-v1",
        model_profile_id=session.model_profile_id,
        action="conclude",
        status=AgentDecisionStatus.TERMINAL,
        summary="Both bounded handoffs are ready for Experiment Design.",
        evidence_refs=(evidence,),
        budget_used=AgentBudgetUsage(model_calls=2, tool_calls=1, tokens=160),
        next_actions=("handoff_experiment_design",),
    )

    first_result = record_agent_decision(first.to_dict(), artifact_store=store)
    second_result = record_agent_decision(second.to_dict(), artifact_store=store)
    after_terminal = build_agent_decision_receipt(
        session_id=session.session_id,
        branch_id="branch-main",
        sequence=3,
        actor="Research Coordinator",
        program_id="coordinator-v1",
        model_profile_id=session.model_profile_id,
        action="revise",
        status=AgentDecisionStatus.ACCEPTED,
        summary="This must not be accepted after terminal state.",
        budget_used=AgentBudgetUsage(model_calls=3, tool_calls=1, tokens=200),
    )
    rejected = record_agent_decision(after_terminal.to_dict(), artifact_store=store)
    resolved = get_agent_decision(second.receipt_id, artifact_store=store)

    assert first_result.ok is True
    assert second_result.ok is True
    assert rejected.ok is False
    assert "terminal research branch" in rejected.errors[0]["message"]
    assert resolved.data["agent_decision_receipt"]["receipt_id"] == second.receipt_id


def test_decision_receipt_rejects_unapproved_program_and_budget_overrun() -> None:
    store = InMemoryResearchArtifactStore()
    session = _session()
    create_agent_session(session.to_dict(), artifact_store=store)
    unapproved = build_agent_decision_receipt(
        session_id=session.session_id,
        branch_id="branch-main",
        sequence=1,
        actor="Research Coordinator",
        program_id="unknown-program",
        model_profile_id=session.model_profile_id,
        action="stop_fail_closed",
        status=AgentDecisionStatus.BLOCKED,
        summary="Program identity is outside the session.",
        budget_used=AgentBudgetUsage(model_calls=99),
        blockers=(ResearchIssue(code="program_denied", message="Denied."),),
    )

    result = record_agent_decision(unapproved.to_dict(), artifact_store=store)

    assert result.ok is False
    assert result.errors[0]["code"] == "agent_decision_recording_failed"


def test_canonical_read_is_exact_governed_and_size_bounded() -> None:
    store = InMemoryResearchArtifactStore()
    record = store.save_artifact(
        artifact_type=DATASET_MANIFEST,
        artifact_id="dataset_demo",
        domain_owner=DATA_DOMAIN_OWNER,
        producer_tool="data_create_research_snapshot",
        payload={"artifact_type": DATASET_MANIFEST, "symbols": ["AAA", "BBB"]},
        status="complete",
    )

    read = read_canonical_artifact(
        record.uri,
        DATASET_MANIFEST,
        artifact_store=store,
    )
    too_small = read_canonical_artifact(
        record.uri,
        DATASET_MANIFEST,
        artifact_store=store,
        max_payload_bytes=1,
    )
    wrong_type = read_canonical_artifact(
        record.uri,
        "data_quality_report",
        artifact_store=store,
    )

    assert read.ok is True
    assert read.data["record"]["payload"]["symbols"] == ["AAA", "BBB"]
    assert len(read.data["record"]["payload_hash"]) == 64
    assert too_small.ok is False
    assert wrong_type.ok is False


def _session() -> ResearchSession:
    return ResearchSession(
        session_id="session-demo",
        objective="Prepare Data and one admitted trend implementation.",
        success_definition="Return exact canonical evidence or a blocker.",
        operator_id="operator-demo",
        approval_policy={
            "data_loading": "preapproved_within_scope",
            "coding_workspace": True,
            "broker_mutation": False,
        },
        scope_envelope={
            "symbols": ["AAA", "BBB"],
            "start": "2025-01-01T00:00:00+00:00",
            "end": "2025-03-01T00:00:00+00:00",
        },
        implementation_specification={
            "implementation_kind": "strategy",
            "signal": "trend",
            "lookback": 20,
        },
        implementation_ref=None,
        python_quality_guide="docs/python_code_quality.md",
        model_profile_id="ollama-qwen35-9b-json-v1",
        agent_program_ids=("coordinator-v1", "data-research-v1", "strategy-engineering-v1"),
        tool_catalog_id="first-slice-tools-v1",
        budget=AgentBudget(
            max_model_calls=12,
            max_tool_calls=24,
            max_tokens=12_000,
            max_duration_seconds=600,
            max_mutations=4,
            max_revisions=2,
            concurrency_limit=2,
        ),
    )
