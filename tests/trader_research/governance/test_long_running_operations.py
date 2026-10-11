"""Contract tests for the selected durable research-operation boundary.

Subject: Backtest, optimisation, walk-forward, and training operation records.
Level: In-process contract.
Collaborators: Typed orchestration values only; no MCP transport, worker, provider,
or database.
Guarantees: Costly operations select durable jobs, public state round-trips, and
ambiguous outcomes require reconciliation before retry.
Non-goals: Executing research operations, selecting a provider, or proving worker
availability.
"""

from __future__ import annotations

import pytest

from trader_research.governance import (
    ResearchIssue,
    ResearchJob,
    ResearchJobStatus,
    ResearchOperationKind,
    ResearchOperationMode,
    artifact_report_ref,
    operation_mode,
)


def _job(**overrides: object) -> ResearchJob:
    values: dict[str, object] = {
        "job_id": "job-123",
        "operation_kind": ResearchOperationKind.BACKTEST,
        "request_ref": "research://postgres/backtest_specification/spec-123",
        "request_digest": "sha256:request",
        "idempotency_key": "request-123",
        "requested_by": "objective-123",
        "actor": "workflow_executor",
        "code_identity": "git:abc123",
        "environment_identity": "env:qualification",
    }
    values.update(overrides)
    return ResearchJob(**values)


def test_all_costly_operations_use_one_durable_job_boundary() -> None:
    """Keep costly operation recovery semantics consistent across future producers."""
    assert {
        kind: operation_mode(kind) for kind in ResearchOperationKind
    } == {
        kind: ResearchOperationMode.DURABLE_JOB for kind in ResearchOperationKind
    }


def test_job_projection_round_trips_without_unbounded_payloads() -> None:
    """Preserve identity, status, and bounded artifact refs across MCP projection."""
    original = _job(
        status=ResearchJobStatus.SUCCEEDED,
        attempt=1,
        produced_artifact_refs=(
            artifact_report_ref("backtest_run", "run-123"),
        ),
    )

    restored = ResearchJob.from_dict(original.to_dict())

    assert restored == original
    assert restored.terminal is True
    assert "prompt" not in original.to_dict()
    assert "credentials" not in original.to_dict()


def test_ambiguous_job_requires_reconciliation_and_cannot_be_retried() -> None:
    """Prevent a lost response from causing an unverified duplicate mutation."""
    blocker = ResearchIssue(
        code="outcome_unknown",
        message="Worker response was lost; inspect canonical child artifacts.",
    )

    job = _job(
        status=ResearchJobStatus.AMBIGUOUS,
        attempt=1,
        blockers=(blocker,),
    )

    assert job.terminal is True
    assert job.retryable is False
    with pytest.raises(ValueError, match="require reconciliation"):
        _job(status=ResearchJobStatus.AMBIGUOUS, retryable=True, blockers=(blocker,))


def test_partial_and_failed_jobs_expose_blockers() -> None:
    """Reject terminal degradation that hides why downstream work must stop."""
    blocker = ResearchIssue(code="child_failed", message="A child operation failed.")
    with pytest.raises(ValueError, match="require blockers"):
        _job(status=ResearchJobStatus.PARTIAL)
    assert _job(status=ResearchJobStatus.PARTIAL, blockers=(blocker,)).terminal is False
    with pytest.raises(ValueError, match="require blockers"):
        _job(status=ResearchJobStatus.FAILED)
    assert _job(status=ResearchJobStatus.FAILED, blockers=(blocker,)).terminal is True
