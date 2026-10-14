"""Canonical producer-shaped blocked decision fixtures for boundary tests."""
from trader_research.foundation import InMemoryResearchArtifactStore, json_payload_hash
from trader_research.governance import BlockedEvidenceBasis, NextDecisionOutcome, build_next_research_decision
from trader_research.governance.artifacts import DOMAIN_OWNER_BY_ARTIFACT_TYPE
from trader_research.governance.handoffs import ArtifactReportRef, ResearchIssue


def blocked_fixture():
    """Retain a minimal producer-shaped blocked outcome and pinned input chain."""
    store = InMemoryResearchArtifactStore()

    def save(kind, identity, payload, status="available", metadata=None):
        record = store.save_artifact(
            artifact_type=kind, artifact_id=identity, payload=payload,
            domain_owner=DOMAIN_OWNER_BY_ARTIFACT_TYPE[kind], producer_tool="fixture",
            status=status, metadata=metadata or {},
        )
        return ArtifactReportRef(
            artifact_type=kind, artifact_id=identity, domain_owner=record.domain_owner,
            uri=record.uri, metadata={"payload_sha256": json_payload_hash(payload)},
        )

    data = save("dataset_manifest", "data-1", {"dataset_id": "data-1"})
    quality = save("data_quality_report", "quality-1", {"dataset_id": "data-1", "status": "passed"})
    strategy = save("implementation_version", "strategy-1", {"implementation_version_id": "strategy-1"})
    risk = save("implementation_version", "risk-1", {"implementation_version_id": "risk-1"})
    run = save("backtest_run", "run-1", {
        "run_id": "run-1", "dataset_id": "data-1", "strategy_implementation_version_id": "strategy-1",
        "risk_lineage": [{"implementation_version_id": "risk-1"}],
    }, "passed")
    objective = save("research_objective", "objective-1", {"objective_id": "objective-1"})
    protocol = save("experiment_protocol", "protocol-1", {
        "protocol_id": "protocol-1", "objective_id": "objective-1",
        "strategy": {"implementation_ref": strategy.to_dict()},
        "risk_managers": [{"implementation_ref": risk.to_dict()}],
        "datasets": [{"dataset_manifest_ref": data.to_dict(), "data_quality_report_ref": quality.to_dict()}],
    }, "approved")
    blockers = (ResearchIssue("review_producer_unavailable", "Independent review is unavailable", {"role": "evaluation", "branch_id": "evaluation-1"}),)
    outcome = save("workflow_outcome", "outcome-1", {
        "artifact_type": "workflow_outcome", "outcome_id": "outcome-1", "workflow_id": "workflow-1",
        "plan_id": "plan-1", "objective_ref": objective.to_dict(), "protocol_ref": protocol.to_dict(),
        "status": "blocked", "produced_artifact_refs": [run.to_dict()], "review_verdict_refs": [],
        "requested_by": "workflow-1", "actor": "workflow-executor",
        "next_permitted_actions": ["review blocked evidence"], "warnings": [], "errors": [],
        "blockers": [item.to_dict() for item in blockers],
    }, "blocked")
    decision = build_next_research_decision(
        decision_id="blocked-choice", revision=1, outcome=NextDecisionOutcome.REJECT,
        rationale="Reject until the missing review evidence can be produced.", operator="human:jared",
        decided_at="2026-10-14T08:00:00Z", source_run_ref=run, data_ref=data,
        implementation_refs=(strategy, risk), assumptions={}, review_refs=(),
        limitations=("Scientific evidence remains unassessed",),
        blocked_evidence=BlockedEvidenceBasis(outcome, blockers),
    )
    return store, decision, save

