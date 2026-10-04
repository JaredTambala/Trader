"""Contracts for human-owned paper-candidate admission.

Subject: Admission identity, evidence pinning, expiry, revocation, and authority.
Level: In-process governance contract with the real artifact store port.
Collaborators: InMemoryResearchArtifactStore and governance ownership registry.
Guarantees: Paper eligibility requires a human decision over unchanged evidence.
Non-goals: Console views, broker mutation, runtime startup, and MCP transport.
"""

from __future__ import annotations

import pytest

from trader_research.foundation import InMemoryResearchArtifactStore, json_payload_hash
from trader_research.governance import (
    PAPER_CANDIDATE_ADMISSION,
    PaperAdmissionDecision,
    PaperCandidateAdmission,
    create_paper_candidate_admission,
    revoke_paper_candidate_admission,
    validate_paper_candidate_admission,
)
from trader_research.governance.artifacts import DOMAIN_OWNER_BY_ARTIFACT_TYPE


NOW = "2026-10-04T10:00:00Z"


def test_human_approval_round_trips_and_is_idempotent() -> None:
    """An approved admission preserves exact versions, limits, and evidence on replay."""
    store = InMemoryResearchArtifactStore()
    _seed_evidence(store)
    payload = _admission_payload()

    created = create_paper_candidate_admission(
        payload,
        artifact_store=store,
        requested_by="human:jared",
        actor="human:jared",
    )
    replay = create_paper_candidate_admission(
        payload,
        artifact_store=store,
        requested_by="human:jared",
        actor="human:jared",
    )

    assert created.ok is True
    assert replay.ok is True
    record = store.load_artifact_record(PAPER_CANDIDATE_ADMISSION, payload["admission_id"])
    admission = PaperCandidateAdmission.from_dict(record.payload)
    assert admission.decision is PaperAdmissionDecision.APPROVED
    assert admission.strategy_version == "strategy-v1"
    assert admission.risk_limits["max_position"] == 0.2
    assert record.requested_by == "human:jared"
    assert validate_paper_candidate_admission(
        payload["admission_id"], artifact_store=store, now=NOW
    ).ok is True


def test_unresolved_limitations_are_explicit_and_digest_pinned() -> None:
    """Admission records retain limitations as part of the immutable decision."""
    store = InMemoryResearchArtifactStore()
    _seed_evidence(store)
    payload = _admission_payload()
    payload["unresolved_limitations"] = ["paper-only evidence", "manual monitoring required"]

    result = create_paper_candidate_admission(
        payload,
        artifact_store=store,
        requested_by="human:jared",
        actor="human:jared",
    )

    assert result.ok is True
    admission = PaperCandidateAdmission.from_dict(
        store.load_artifact_record(PAPER_CANDIDATE_ADMISSION, payload["admission_id"]).payload
    )
    assert admission.unresolved_limitations == (
        "paper-only evidence",
        "manual monitoring required",
    )
    assert admission.to_dict()["unresolved_limitations"] == [
        "paper-only evidence",
        "manual monitoring required",
    ]


def test_missing_or_changed_evidence_blocks_creation_and_validation() -> None:
    """Admission creation and later validation fail closed when evidence changes."""
    store = InMemoryResearchArtifactStore()
    _seed_evidence(store)
    payload = _admission_payload()
    payload["evidence_refs"]["backtest"]["metadata"]["version"] = "strategy-v2"

    changed_version = create_paper_candidate_admission(
        payload,
        artifact_store=store,
        requested_by="human:jared",
        actor="human:jared",
    )
    assert changed_version.ok is False
    assert "version has changed" in changed_version.errors[0]["message"]

    payload = _admission_payload()
    assert create_paper_candidate_admission(
        payload,
        artifact_store=store,
        requested_by="human:jared",
        actor="human:jared",
    ).ok is True
    store.save_artifact(
        artifact_type="backtest_run",
        artifact_id="backtest-1",
        domain_owner="Experiments",
        producer_tool="fixture_changed",
        payload={"artifact_type": "backtest_run", "run_id": "backtest-1", "result": "changed"},
        status="completed",
        source_hash="changed-source",
    )
    result = validate_paper_candidate_admission(
        payload["admission_id"], artifact_store=store, now=NOW
    )
    assert result.ok is False
    assert "payload has changed" in result.errors[0]["message"]


@pytest.mark.parametrize(
    ("decision", "expected"),
    [
        ("rejected", "admission decision is rejected"),
        ("revoked", "admission decision is revoked"),
    ],
)
def test_rejection_and_expiry_are_not_paper_eligible(decision: str, expected: str) -> None:
    """Rejected or expired decisions never satisfy the paper-start gate."""
    store = InMemoryResearchArtifactStore()
    _seed_evidence(store)
    payload = _admission_payload()
    payload["admission_id"] = f"admission-{decision}"
    payload["decision"] = decision
    if decision == "rejected":
        payload.pop("expires_at")
    else:
        payload["revoked_at"] = NOW
        payload["revocation_reason"] = "operator withdrew candidate"
    assert create_paper_candidate_admission(
        payload,
        artifact_store=store,
        requested_by="human:jared",
        actor="human:jared",
    ).ok is True
    result = validate_paper_candidate_admission(payload["admission_id"], artifact_store=store, now=NOW)
    assert result.ok is False
    assert expected in result.errors[0]["message"]

    expired = _admission_payload()
    expired["admission_id"] = "admission-expired"
    expired["expires_at"] = "2026-10-03T10:00:00Z"
    assert create_paper_candidate_admission(
        expired,
        artifact_store=store,
        requested_by="human:jared",
        actor="human:jared",
    ).ok is True
    expiry_result = validate_paper_candidate_admission("admission-expired", artifact_store=store, now=NOW)
    assert expiry_result.ok is False
    assert "admission has expired" in expiry_result.errors[0]["message"]


def test_revocation_creates_human_owned_successor_without_mutating_original() -> None:
    """Revocation appends a successor and leaves the approved record immutable."""
    store = InMemoryResearchArtifactStore()
    _seed_evidence(store)
    payload = _admission_payload()
    assert create_paper_candidate_admission(
        payload,
        artifact_store=store,
        requested_by="human:jared",
        actor="human:jared",
    ).ok is True
    revoked = revoke_paper_candidate_admission(
        payload["admission_id"],
        reason="risk limit changed",
        approver="human:jared",
        artifact_store=store,
        now=NOW,
    )
    assert revoked.ok is True
    successor = revoked.data["paper_candidate_admission"]
    assert successor["decision"] == "revoked"
    assert successor["supersedes_admission_id"] == payload["admission_id"]
    assert store.load_artifact_record(PAPER_CANDIDATE_ADMISSION, payload["admission_id"]).payload["decision"] == "approved"
    assert validate_paper_candidate_admission(payload["admission_id"], artifact_store=store, now=NOW).ok is False
    assert validate_paper_candidate_admission(successor["admission_id"], artifact_store=store, now=NOW).ok is False


@pytest.mark.parametrize("principal", ["Data Agent", "Research Coordinator", "mcp:paper_create_candidate_admission"])
def test_agents_and_mcp_cannot_create_or_approve(principal: str) -> None:
    """Registered agent and MCP identities cannot cross the human admission boundary."""
    store = InMemoryResearchArtifactStore()
    _seed_evidence(store)
    result = create_paper_candidate_admission(
        _admission_payload(),
        artifact_store=store,
        requested_by=principal,
        actor=principal,
    )
    assert result.ok is False
    assert "human principal" in result.errors[0]["message"]


def test_unprefixed_service_identity_cannot_cross_human_gate() -> None:
    """A service-like identity without the human principal namespace is rejected."""
    store = InMemoryResearchArtifactStore()
    _seed_evidence(store)
    result = create_paper_candidate_admission(
        _admission_payload(),
        artifact_store=store,
        requested_by="operator-service",
        actor="operator-service",
    )
    assert result.ok is False
    assert "human principal" in result.errors[0]["message"]


def _seed_evidence(store: InMemoryResearchArtifactStore) -> None:
    """Store deterministic evidence records with the fields pinned by admission."""
    for artifact_type, artifact_id, payload, source_hash in (
        (
            "backtest_run",
            "backtest-1",
            {"artifact_type": "backtest_run", "run_id": "backtest-1", "version": "strategy-v1"},
            "backtest-source-v1",
        ),
        (
            "evaluation_report",
            "evaluation-1",
            {"artifact_type": "evaluation_report", "report_id": "evaluation-1", "version": "evaluation-v1"},
            "evaluation-source-v1",
        ),
    ):
        store.save_artifact(
            artifact_type=artifact_type,
            artifact_id=artifact_id,
            domain_owner=DOMAIN_OWNER_BY_ARTIFACT_TYPE[artifact_type],
            producer_tool="fixture",
            payload=payload,
            status="passed",
            source_hash=source_hash,
        )


def _admission_payload() -> dict[str, object]:
    """Build a complete approved admission fixture."""
    refs = {
        "backtest": _ref("backtest_run", "backtest-1", "strategy-v1", "backtest-source-v1"),
        "evaluation": _ref("evaluation_report", "evaluation-1", "evaluation-v1", "evaluation-source-v1"),
    }
    return {
        "artifact_type": PAPER_CANDIDATE_ADMISSION,
        "schema_version": "1",
        "admission_id": "admission-approved",
        "candidate_ref": "strategy-candidate-1",
        "evidence_refs": refs,
        "strategy_version": "strategy-v1",
        "risk_version": "risk-v1",
        "data_version": "dataset-v1",
        "risk_limits": {"max_position": 0.2, "max_daily_loss": 0.03},
        "broker_scope": {"environment": "paper", "account": "paper-account-1"},
        "monitoring_policy": {"heartbeat_seconds": 30, "drift_check": "daily"},
        "decision": "approved",
        "approver": "human:jared",
        "decided_at": NOW,
        "expires_at": "2026-10-11T10:00:00Z",
    }


def _ref(artifact_type: str, artifact_id: str, version: str, source_hash: str) -> dict[str, object]:
    """Build a fully pinned canonical artifact reference."""
    payload = {
        "artifact_type": artifact_type,
        "run_id" if artifact_type == "backtest_run" else "report_id": artifact_id,
        "version": version,
    }
    return {
        "artifact_type": artifact_type,
        "artifact_id": artifact_id,
        "domain_owner": DOMAIN_OWNER_BY_ARTIFACT_TYPE[artifact_type],
        "uri": f"research://postgres/{artifact_type}/{artifact_id}",
        "metadata": {
            "payload_sha256": json_payload_hash(payload),
            "source_hash": source_hash,
            "version": version,
        },
    }
