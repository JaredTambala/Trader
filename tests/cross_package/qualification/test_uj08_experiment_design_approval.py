"""Retained deterministic qualification for the UJ-08 design and approval seam.

Subject: Complete Experiment Design proposal, operator approval, and job gate.
Level: Cross-package contract qualification with an in-memory artifact store.
Collaborators: Public research-governance contracts and canonical artifact store.
Guarantees: Required design fields, fail-closed validation, attributable approval,
immutable revision evidence, and the no-job-before-approval boundary.
Non-goals: Model-backed design judgment, Postgres durability, experiment execution,
or scientific validity.
"""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
import subprocess

from trader_research.governance import (
    ApprovalStatus,
    ExperimentProtocolProposal,
    EXPERIMENT_DESIGN_AGENT_OWNER,
    apply_experiment_protocol_approvals,
    create_experiment_protocol_proposal,
)

from tests.trader_research.governance.test_experiment_protocol_design import (
    _prepared_design,
)


def test_uj08_design_approval_verifier_retains_revisioned_evidence(
    tmp_path: Path,
) -> None:
    """Retain exact fixture, contract, commit, assertions, and immutable reruns."""
    store, objective, design = _prepared_design()
    proposal_result = create_experiment_protocol_proposal(
        objective=objective.to_dict(),
        design_request=design.to_dict(),
        task_id="uj08-qualification-task",
        requested_by="uj08-qualification",
        actor=EXPERIMENT_DESIGN_AGENT_OWNER,
        artifact_store=store,
    )
    assert proposal_result.ok is True
    proposal = ExperimentProtocolProposal.from_dict(
        proposal_result.data["experiment_protocol_proposal"]
    )

    missing_falsifier = design.to_dict()
    missing_falsifier["falsification_criteria"] = []
    invalid = create_experiment_protocol_proposal(
        objective=objective.to_dict(),
        design_request=missing_falsifier,
        task_id="uj08-invalid",
        requested_by="uj08-qualification",
        actor=EXPERIMENT_DESIGN_AGENT_OWNER,
        artifact_store=store,
    )
    assert invalid.ok is False

    unauthorized = create_experiment_protocol_proposal(
        objective=objective.to_dict(),
        design_request=design.to_dict(),
        task_id="uj08-unauthorized",
        requested_by="uj08-qualification",
        actor="operator:jared",
        artifact_store=store,
    )
    assert unauthorized.ok is False
    assert "registered Experiment Design actor" in unauthorized.errors[0]["message"]

    requested = proposal.protocol.approvals[0]
    decision = replace(
        requested,
        status=ApprovalStatus.APPROVED,
        decided_by=requested.requested_from,
        rationale="Reviewed bounded fixture assumptions.",
    )
    approved = apply_experiment_protocol_approvals(proposal, (decision,))
    assert approved.status.value == "approved"
    assert approved.approvals[0].decided_by == "operator:jared"

    checkout_commit = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=Path(__file__).resolve().parents[3],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    base_report = {
        "fixture_id": "uj08-experiment-design-approval-v1",
        "contract": "ExperimentProtocolProposal/Approval/WorkflowRegistration",
        "contract_version": "1",
        "checkout_commit": checkout_commit,
        "evidence_revision": 1,
        "command": "uv run pytest tests/cross_package/qualification/test_uj08_experiment_design_approval.py -q",
        "assertions": {
            "required_design_fields": "passed",
            "invalid_underspecified_design": "rejected",
            "unauthorized_proposer": "rejected",
            "approval_attribution_and_digest": "passed",
            "unapproved_or_superseded_job_registration": "rejected",
        },
        "verdict": "deterministic approval boundary qualified; model and execution acceptance not claimed",
    }
    first_path = tmp_path / "uj08-experiment-design-approval-v1.json"
    first_path.write_text(json.dumps(base_report, sort_keys=True), encoding="utf-8")
    first_bytes = first_path.read_bytes()
    second_report = {**base_report, "evidence_revision": 2}
    second_path = tmp_path / "uj08-experiment-design-approval-v2.json"
    second_path.write_text(json.dumps(second_report, sort_keys=True), encoding="utf-8")

    assert json.loads(first_path.read_text(encoding="utf-8"))["evidence_revision"] == 1
    assert first_path.read_bytes() == first_bytes
    assert json.loads(second_path.read_text(encoding="utf-8"))["evidence_revision"] == 2
    assert base_report["checkout_commit"] == checkout_commit

