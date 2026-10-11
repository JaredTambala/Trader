"""Retained UJ-08 qualification for independent evidence joins.

Subject: Experiment Design proposal and approval through run, review, decision,
and retained public trajectory evidence.
Level: Deterministic cross-package qualification with an in-memory artifact store.
Collaborators: Research governance/review contracts and the retained agent
trajectory verifier; no model, MCP, Postgres, browser, or broker.
Guarantees: Exact proposal, approval, scope, implementation, run, review, and
revision identities are joined; review limitations and negative states survive;
a fresh process reopens the public verifier output.
Non-goals: Scientific validity, worker durability, controlled model acceptance,
or paper-trading authorization.
"""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

from trader_agents import verify_retained_trajectory
from trader_research.foundation import json_payload_hash
from trader_research.governance import (
    ApprovalStatus,
    EXPERIMENT_PROTOCOL,
    EXPERIMENT_PROTOCOL_PROPOSAL,
    EXPERIMENT_DESIGN_AGENT_OWNER,
    ExperimentProtocolProposal,
    Approval,
    IMPLEMENTATION_VERSION,
    RESEARCH_OBJECTIVE,
    WorkflowOutcome,
    WorkflowOutcomeStatus,
    WORKFLOW_OUTCOME,
    apply_experiment_protocol_approvals,
    create_experiment_protocol_proposal,
)
from trader_research.governance.artifacts import (
    APPROVAL_REQUEST,
    BACKTEST_RUN,
    DATASET_MANIFEST,
    EVALUATION_REPORT,
    ROBUSTNESS_REPORT,
)
from trader_research.governance.handoffs import ArtifactReportRef
from trader_research.review import (
    EvidenceJoinRef,
    EvidenceJoinStatus,
    qualify_evidence_join,
)
from tests.trader_agents.observability.support.retained_trajectory import (
    build_retained_trajectory_fixture,
)
from tests.trader_research.governance.test_experiment_protocol_design import (
    _prepared_design,
)


def test_uj08_retains_exact_evidence_join_and_reopens_in_fresh_process(
    tmp_path: Path,
) -> None:
    """Join canonical proposal, approval, run, reviews, decision, and trajectory evidence."""
    store, objective, design = _prepared_design()
    proposal_result = create_experiment_protocol_proposal(
        objective=objective.to_dict(),
        design_request=design.to_dict(),
        task_id="uj08-evidence-join",
        requested_by="uj08-evidence-join",
        actor=EXPERIMENT_DESIGN_AGENT_OWNER,
        artifact_store=store,
    )
    assert proposal_result.ok, proposal_result.errors
    proposal_payload = proposal_result.data["experiment_protocol_proposal"]
    proposal = proposal_result.data["experiment_protocol_proposal"]
    proposal_record = store.load_artifact_record(
        EXPERIMENT_PROTOCOL_PROPOSAL,
        proposal_payload["proposal_id"],
    )

    objective_record = store.save_artifact(
        artifact_type=RESEARCH_OBJECTIVE,
        artifact_id=objective.objective_id,
        domain_owner="Orchestration",
        producer_tool="research_create_research_objective",
        payload=objective.to_dict(),
        status="approved",
    )
    requested = proposal_payload["protocol"]["approvals"][0]
    approved_protocol = apply_experiment_protocol_approvals(
        ExperimentProtocolProposal.from_dict(proposal),
        [
            Approval.from_dict(
                {
                    **requested,
                    "status": ApprovalStatus.APPROVED.value,
                    "decided_by": requested["requested_from"],
                    "rationale": "Operator reviewed the bounded fixture assumption.",
                }
            )
        ],
    )
    store.save_artifact(
        artifact_type=EXPERIMENT_PROTOCOL,
        artifact_id=approved_protocol.protocol_id,
        domain_owner="Experiments",
        producer_tool="research_register_experiment_workflow",
        payload=approved_protocol.to_dict(),
        status="approved",
    )
    approval_record = store.save_artifact(
        artifact_type=APPROVAL_REQUEST,
        artifact_id=requested["approval_id"],
        domain_owner="Orchestration",
        producer_tool="research_create_experiment_protocol_proposal",
        payload={**requested, "status": ApprovalStatus.APPROVED.value, "decided_by": requested["requested_from"], "rationale": "Operator reviewed the bounded fixture assumption."},
        status="approved",
    )

    manifest = design.datasets[0].dataset_manifest_ref
    strategy = design.strategy.implementation_ref
    scope_id = manifest.artifact_id
    strategy_version_id = strategy.artifact_id
    run_id = "uj08-run-1"
    lineage = {
        "experiment_id": approved_protocol.protocol_id,
        "proposal_id": proposal_payload["proposal_id"],
        "scope_id": scope_id,
        "strategy_version_id": strategy_version_id,
        "run_id": run_id,
    }
    run_record = store.save_artifact(
        artifact_type=BACKTEST_RUN,
        artifact_id=run_id,
        domain_owner="Experiments",
        producer_tool="research_execute_experiment_protocol",
        payload={"artifact_type": BACKTEST_RUN, **lineage, "status": "completed", "summary": {"return": 0.02}},
        status="completed",
        metadata={**lineage, "revision": 1},
    )
    evaluation_record = store.save_artifact(
        artifact_type=EVALUATION_REPORT,
        artifact_id="uj08-evaluation-1",
        domain_owner="Review",
        producer_tool="evaluation_review_experiment",
        payload={"artifact_type": EVALUATION_REPORT, **lineage, "status": "inconclusive", "limitations": ["One market regime"]},
        status="available",
        metadata={**lineage, "revision": 1, "statistical_status": "inconclusive", "comparison_status": "eligible"},
    )
    robustness_record = store.save_artifact(
        artifact_type=ROBUSTNESS_REPORT,
        artifact_id="uj08-robustness-1",
        domain_owner="Review",
        producer_tool="adversarial_review_experiment",
        payload={"artifact_type": ROBUSTNESS_REPORT, **lineage, "status": "negative", "limitations": ["Stress evidence is negative"]},
        status="negative",
        metadata={**lineage, "revision": 1, "robustness_status": "fail"},
    )
    objective_ref = _record_ref(objective_record)
    protocol_ref = _record_ref(store.load_artifact_record(EXPERIMENT_PROTOCOL, approved_protocol.protocol_id))
    run_ref = _record_ref(run_record)
    evaluation_ref = _record_ref(evaluation_record)
    robustness_ref = _record_ref(robustness_record)
    outcome = WorkflowOutcome(
        outcome_id="uj08-decision-1",
        workflow_id="uj08-workflow-1",
        plan_id="uj08-plan-1",
        objective_ref=objective_ref,
        protocol_ref=protocol_ref,
        status=WorkflowOutcomeStatus.COMPLETED,
        produced_artifact_refs=(run_ref, evaluation_ref, robustness_ref),
        review_verdict_refs=(evaluation_ref, robustness_ref),
        requested_by="uj08-evidence-join",
        actor="research_coordinator",
        next_permitted_actions=("record_human_next_decision",),
    )
    decision_record = store.save_artifact(
        artifact_type=WORKFLOW_OUTCOME,
        artifact_id=outcome.outcome_id,
        domain_owner="Orchestration",
        producer_tool="research_record_workflow_outcome",
        payload=outcome.to_dict(),
        status="completed",
        metadata={**lineage, "revision": 1, "statistical_status": "inconclusive", "robustness_status": "fail", "comparison_status": "eligible"},
    )
    records = (
        _join_ref("proposal", proposal_record, lineage={"experiment_id": approved_protocol.protocol_id, "proposal_id": proposal_payload["proposal_id"]}),
        _join_ref("approval", approval_record, lineage={"experiment_id": approved_protocol.protocol_id, "proposal_id": proposal_payload["proposal_id"]}),
        _join_ref("scope", store.load_artifact_record(DATASET_MANIFEST, scope_id), lineage={"experiment_id": approved_protocol.protocol_id, "proposal_id": proposal_payload["proposal_id"], "scope_id": scope_id}),
        _join_ref("strategy", store.load_artifact_record(IMPLEMENTATION_VERSION, strategy_version_id), lineage={"experiment_id": approved_protocol.protocol_id, "proposal_id": proposal_payload["proposal_id"], "strategy_version_id": strategy_version_id}),
        _join_ref("run", run_record, lineage=lineage),
        _join_ref("evaluation", evaluation_record, lineage=lineage, limitations=("One market regime",), statistical_status="inconclusive", comparison_status="eligible"),
        _join_ref("robustness", robustness_record, lineage=lineage, status=EvidenceJoinStatus.NEGATIVE, limitations=("Stress evidence is negative",), robustness_status="fail"),
        _join_ref("decision", decision_record, lineage=lineage, comparison_status="eligible"),
    )
    joined = qualify_evidence_join(
        experiment_id=approved_protocol.protocol_id,
        proposal_id=proposal_payload["proposal_id"],
        scope_id=scope_id,
        strategy_version_id=strategy_version_id,
        run_id=run_id,
        evidence_revision=1,
        records=records,
    )
    assert joined.verdict.value == "partial"
    assert joined.terminal_summary["statistical_status"] == "inconclusive"
    assert joined.terminal_summary["robustness_status"] == "fail"
    assert "Stress evidence is negative" in joined.terminal_summary["limitations"]

    trajectory = build_retained_trajectory_fixture()
    trajectory_verdict = verify_retained_trajectory(trajectory)
    assert trajectory_verdict["terminal_decision_lineage"] is True

    checkout_commit = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=Path(__file__).resolve().parents[3],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    report = {
        "fixture_id": "uj08-evidence-join-v1",
        "contract": "EvidenceJoinRef/EvidenceJoinResult",
        "contract_version": "1",
        "checkout_commit": checkout_commit,
        "evidence_revision": joined.evidence_revision,
        "command": "uv run pytest tests/cross_package/qualification/test_uj08_evidence_join.py -q",
        "join": joined.to_dict(),
        "trajectory_verdict": trajectory_verdict,
        "fresh_process_recovered": True,
    }
    report_path = tmp_path / "uj08-evidence-join-verifier.json"
    report_path.write_text(json.dumps(report, sort_keys=True), encoding="utf-8")
    reopened = subprocess.run(
        [
            sys.executable,
            "-c",
            "import json,sys; from trader_research.review import EvidenceJoinResult; print(json.dumps(EvidenceJoinResult.from_dict(json.load(open(sys.argv[1]))['join']).to_dict(), sort_keys=True))",
            str(report_path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    assert json.loads(reopened.stdout) == joined.to_dict()
    assert json.loads(report_path.read_text(encoding="utf-8"))["checkout_commit"] == checkout_commit


def _record_ref(record) -> ArtifactReportRef:
    """Build a pinned typed reference from one canonical record."""
    return ArtifactReportRef(
        artifact_id=record.artifact_id,
        artifact_type=record.artifact_type,
        domain_owner=record.domain_owner,
        uri=record.uri,
        metadata={"payload_sha256": json_payload_hash(record.payload)},
    )


def _join_ref(
    role: str,
    record,
    *,
    lineage: dict[str, str],
    status: EvidenceJoinStatus = EvidenceJoinStatus.AVAILABLE,
    limitations: tuple[str, ...] = (),
    statistical_status: str | None = None,
    robustness_status: str | None = None,
    comparison_status: str | None = None,
) -> EvidenceJoinRef:
    """Normalize one canonical record to the public exact-join contract."""
    return EvidenceJoinRef(
        role=role,
        reference=ArtifactReportRef(
            artifact_id=record.artifact_id,
            artifact_type=record.artifact_type,
            domain_owner=record.domain_owner,
            uri=record.uri,
            metadata={"payload_sha256": json_payload_hash(record.payload)},
        ),
        revision=int(record.metadata.get("revision", 1)),
        status=status,
        lineage=lineage,
        limitations=limitations,
        statistical_status=statistical_status,
        robustness_status=robustness_status,
        comparison_status=comparison_status,
    )
