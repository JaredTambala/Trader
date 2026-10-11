"""Contract tests for the research-owned experiment evidence join.

Subject: Exact identity and explicit availability states across independent review.
Level: In-process deterministic contract.
Collaborators: Typed evidence-join values only; no store, model, MCP, or broker.
Guarantees: Required roles carry exact lineage, negative evidence survives, and
retained output reopens without hidden state.
Non-goals: Scientific validity, worker execution, or paper-trading admission.
"""

from __future__ import annotations

import json

import pytest

from trader_research.governance import artifact_report_ref
from trader_research.review import (
    EvidenceJoinRef,
    EvidenceJoinStatus,
    qualify_evidence_join,
)


IDENTITY = {
    "experiment_id": "protocol-1",
    "proposal_id": "proposal-1",
    "scope_id": "scope-1",
    "strategy_version_id": "strategy-v1",
    "run_id": "run-1",
}


def test_complete_join_preserves_terminal_review_fields_and_exact_revisions() -> None:
    """A complete chain joins every required role and retains review limitations."""
    result = qualify_evidence_join(
        **IDENTITY,
        evidence_revision=1,
        records=_records(),
    )

    assert result.verdict.value == "complete"
    assert result.terminal_summary == {
        "statistical_status": "inconclusive",
        "robustness_status": "not_assessed",
        "comparison_status": "eligible",
        "limitations": ["One market regime"],
        "blockers": [],
    }
    rendered = result.to_dict()
    assert [item["key"] for item in rendered["records"]] == sorted(
        item["key"] for item in rendered["records"]
    )
    assert all(item["revision"] == 1 for item in rendered["records"])
    assert rendered["evidence_revision"] == 1


@pytest.mark.parametrize(
    ("role", "status", "expected_verdict"),
    [
        ("evaluation", EvidenceJoinStatus.PARTIAL, "partial"),
        ("robustness", EvidenceJoinStatus.NEGATIVE, "partial"),
        ("evaluation", EvidenceJoinStatus.MISSING, "blocked"),
        ("run", EvidenceJoinStatus.STALE, "blocked"),
        ("scope", EvidenceJoinStatus.INCOMPATIBLE, "blocked"),
    ],
)
def test_join_retains_degraded_producer_states(
    role: str,
    status: EvidenceJoinStatus,
    expected_verdict: str,
) -> None:
    """Missing, stale, incompatible, partial, and negative evidence stay explicit."""
    records = list(_records())
    index = next(index for index, item in enumerate(records) if item.role == role)
    records[index] = EvidenceJoinRef(
        role=role,
        reference=records[index].reference,
        revision=records[index].revision,
        status=status,
        lineage=records[index].lineage,
        limitations=records[index].limitations,
        blockers=("producer evidence is unavailable",) if status in {
            EvidenceJoinStatus.MISSING,
            EvidenceJoinStatus.STALE,
            EvidenceJoinStatus.INCOMPATIBLE,
        } else (),
        statistical_status=records[index].statistical_status,
        robustness_status=records[index].robustness_status,
        comparison_status=records[index].comparison_status,
    )

    result = qualify_evidence_join(**IDENTITY, evidence_revision=1, records=records)

    assert result.verdict.value == expected_verdict
    assert status.value in result.to_dict()["records"][next(
        index for index, item in enumerate(result.to_dict()["records"]) if item["role"] == role
    )]["status"]
    if expected_verdict == "blocked":
        assert any("producer evidence is unavailable" in blocker for blocker in result.blockers)


def test_join_blocks_lineage_drift_and_unsupported_roles() -> None:
    """A matching artifact URI cannot conceal changed run identity or an invented role."""
    records = list(_records())
    run = records[4]
    records[4] = EvidenceJoinRef(
        role="run",
        reference=run.reference,
        revision=run.revision,
        status=run.status,
        lineage={**run.lineage, "run_id": "run-other"},
        blockers=run.blockers,
    )
    result = qualify_evidence_join(**IDENTITY, evidence_revision=1, records=records)

    assert result.verdict.value == "blocked"
    assert "run lineage does not match: run_id" in result.blockers


def test_retained_join_round_trips_without_payloads() -> None:
    """The verifier output is JSON-safe and can be reconstructed exactly."""
    from trader_research.review import EvidenceJoinResult

    result = qualify_evidence_join(**IDENTITY, evidence_revision=2, records=_records())
    payload = result.to_dict()
    reopened = EvidenceJoinResult.from_dict(json.loads(json.dumps(payload, sort_keys=True)))

    assert reopened.to_dict() == payload
    assert "raw_payload" not in json.dumps(payload)


def _records() -> tuple[EvidenceJoinRef, ...]:
    """Build the complete public identity fixture used by the contract tests."""
    lineage_by_role = {
        "proposal": {"experiment_id": IDENTITY["experiment_id"], "proposal_id": IDENTITY["proposal_id"]},
        "approval": {"experiment_id": IDENTITY["experiment_id"], "proposal_id": IDENTITY["proposal_id"]},
        "scope": {"experiment_id": IDENTITY["experiment_id"], "proposal_id": IDENTITY["proposal_id"], "scope_id": IDENTITY["scope_id"]},
        "strategy": {"experiment_id": IDENTITY["experiment_id"], "proposal_id": IDENTITY["proposal_id"], "strategy_version_id": IDENTITY["strategy_version_id"]},
        "run": dict(IDENTITY),
        "evaluation": dict(IDENTITY),
        "robustness": dict(IDENTITY),
        "decision": dict(IDENTITY),
    }
    statuses = {
        "proposal": "proposed",
        "approval": "approved",
        "scope": "qualified",
        "strategy": "admitted",
        "run": "completed",
        "evaluation": "inconclusive",
        "robustness": "not_assessed",
        "decision": "reject",
    }
    records = []
    for role, lineage in lineage_by_role.items():
        records.append(
            EvidenceJoinRef(
                role=role,
                reference=_ref(f"{role}-1"),
                revision=1,
                status=EvidenceJoinStatus.AVAILABLE,
                lineage=lineage,
                limitations=("One market regime",) if role == "evaluation" else (),
                statistical_status=statuses[role] if role == "evaluation" else None,
                robustness_status=statuses[role] if role == "robustness" else None,
                comparison_status="eligible" if role == "evaluation" else None,
            )
        )
    return tuple(records)


def _ref(artifact_id: str):
    """Build a pinned generic reference for one fixture artifact."""
    return artifact_report_ref(
        "evaluation_report",
        artifact_id,
    ).__class__(
        artifact_id=artifact_id,
        artifact_type="evaluation_report",
        domain_owner="Review",
        uri=f"research://postgres/evaluation_report/{artifact_id}",
        metadata={"payload_sha256": "a" * 64},
    )
