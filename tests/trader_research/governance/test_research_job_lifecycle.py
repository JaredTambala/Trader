"""Contracts for deterministic durable research-job commands.

Subject: Submit, status, cancellation, and reconciliation application commands.
Level: In-process service contract over a Postgres-shaped store port.
Collaborators: ``ResearchJob`` and a small store double; no worker, provider,
MCP transport, or operation-specific producer.
Guarantees: Exact admission replay is idempotent, identity and authority drift
fail closed, and cancellation/reconciliation retain bounded lineage fields.
Non-goals: Worker scheduling, lease acquisition, retry-attempt persistence, and
provider or child-artifact discovery.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any, cast

import pytest

from trader_research.governance import (
    ResearchIssue,
    ResearchJob,
    ResearchJobStatus,
    ResearchOperationKind,
    ResearchJobLifecycleService,
    artifact_report_ref,
)
from trader_research.infrastructure.postgres.job_store import (
    ResearchJobConflict,
    ResearchJobNotFound,
    ResearchJobTransitionError,
)


def _job(**overrides: object) -> ResearchJob:
    """Build one valid queued fixture."""
    base = ResearchJob(
        job_id="job-lifecycle-1",
        operation_kind=ResearchOperationKind.BACKTEST,
        request_ref="research://postgres/backtest_specification/spec-1",
        request_digest="sha256:request-1",
        idempotency_key="request-1",
        requested_by="workflow-executor",
        actor="workflow-executor",
        code_identity="git:commit-1",
        environment_identity="env:qualification",
    )
    return replace(base, **cast(Any, overrides))


@dataclass
class _MemoryJobStore:
    """Store double with the same transition semantics as the Postgres adapter."""

    jobs: dict[str, ResearchJob]

    def __init__(self) -> None:
        self.jobs = {}

    def admit(self, job: ResearchJob) -> ResearchJob:
        existing = next(
            (item for item in self.jobs.values() if item.idempotency_key == job.idempotency_key),
            None,
        )
        if existing is not None:
            for field in (
                "operation_kind",
                "request_ref",
                "request_digest",
                "idempotency_key",
                "requested_by",
                "actor",
                "code_identity",
                "environment_identity",
            ):
                if getattr(existing, field) != getattr(job, field):
                    raise ResearchJobConflict(f"research job {field} conflicts")
            return existing
        if job.job_id in self.jobs:
            raise ResearchJobConflict("job_id already exists")
        self.jobs[job.job_id] = job
        return job

    def load(self, job_id: str) -> ResearchJob:
        try:
            return self.jobs[job_id]
        except KeyError as exc:
            raise ResearchJobNotFound(job_id) from exc

    def save(
        self,
        job: ResearchJob,
        *,
        expected_status: ResearchJobStatus | None = None,
    ) -> ResearchJob:
        current = self.load(job.job_id)
        if expected_status is not None and current.status is not expected_status:
            raise ResearchJobTransitionError("status changed")
        if current.terminal:
            raise ResearchJobTransitionError("terminal job")
        self.jobs[job.job_id] = job
        return job


def test_submit_and_status_are_exactly_idempotent() -> None:
    """Repeated admission and reread return one bounded queued projection."""
    store = _MemoryJobStore()
    service = ResearchJobLifecycleService(store)
    first = service.submit(_job())
    replay = service.submit(_job(job_id="different-generated-id"))

    assert first.ok is True
    assert replay.ok is True
    assert first.data == replay.data
    assert service.status("job-lifecycle-1").data == first.data


def test_submit_conflicting_identity_fails_closed() -> None:
    """A changed request digest cannot reuse an accepted idempotency key."""
    service = ResearchJobLifecycleService(_MemoryJobStore())
    assert service.submit(_job()).ok is True

    result = service.submit(_job(request_digest="sha256:changed"))

    assert result.ok is False
    assert result.errors[0]["code"] == "research_job_submission_failed"
    assert "conflicts" in result.errors[0]["message"]


def test_cancel_requires_authority_and_preserves_lineage() -> None:
    """Cancellation retains actor, attempt, child refs, warnings, and blockers."""
    blocker = ResearchIssue(code="child_waiting", message="child remains unresolved")
    warning = ResearchIssue(code="slow_worker", message="worker is slow")
    child = artifact_report_ref("backtest_run", "run-1")
    job = _job(
        status=ResearchJobStatus.RUNNING,
        attempt=2,
        lease_id="lease-2",
        produced_artifact_refs=(child,),
        warnings=(warning,),
        blockers=(blocker,),
    )
    store = _MemoryJobStore()
    store.jobs[job.job_id] = job
    service = ResearchJobLifecycleService(store)

    unauthorized = service.cancel(job.job_id, actor="other-actor", reason="stop")
    cancelled = service.cancel(job.job_id, actor=job.actor, reason="stop")
    replay = service.cancel(job.job_id, actor=job.actor, reason="stop")

    assert unauthorized.ok is False
    assert cancelled.ok is True
    projection = ResearchJob.from_dict(cancelled.data["research_job"])
    assert projection.status is ResearchJobStatus.CANCELLED
    assert projection.actor == job.actor
    assert projection.attempt == job.attempt
    assert projection.produced_artifact_refs == (child,)
    assert projection.warnings == (warning,)
    assert projection.blockers[:1] == (blocker,)
    assert projection.blockers[-1].code == "operator_cancelled"
    assert replay.data == cancelled.data


def test_reconcile_appends_evidence_and_preserves_existing_blockers() -> None:
    """A canonical terminal outcome retains all prior bounded lineage."""
    existing_blocker = ResearchIssue(code="worker_timeout", message="worker timed out")
    new_blocker = ResearchIssue(code="provider_unknown", message="provider was queried")
    child = artifact_report_ref("backtest_run", "run-2")
    job = _job(
        status=ResearchJobStatus.PARTIAL,
        attempt=3,
        produced_artifact_refs=(child,),
        blockers=(existing_blocker,),
    )
    store = _MemoryJobStore()
    store.jobs[job.job_id] = job

    result = ResearchJobLifecycleService(store).reconcile(
        job.job_id,
        actor=job.actor,
        status=ResearchJobStatus.FAILED,
        produced_artifact_refs=(child, artifact_report_ref("evaluation_report", "eval-2")),
        blockers=(new_blocker,),
    )

    assert result.ok is True
    projection = ResearchJob.from_dict(result.data["research_job"])
    assert projection.status is ResearchJobStatus.FAILED
    assert projection.actor == job.actor
    assert projection.attempt == 3
    assert [item.uri for item in projection.produced_artifact_refs] == [
        child.uri,
        "research://postgres/evaluation_report/eval-2",
    ]
    assert projection.blockers == (existing_blocker, new_blocker)


@pytest.mark.parametrize("status", [ResearchJobStatus.AMBIGUOUS, ResearchJobStatus.RECONCILIATION_REQUIRED])
def test_reconcile_requires_blocker_for_uncertain_outcome(status: ResearchJobStatus) -> None:
    """Unknown outcomes cannot be accepted without an explicit blocker."""
    store = _MemoryJobStore()
    job = _job(status=ResearchJobStatus.RUNNING)
    store.jobs[job.job_id] = job

    result = ResearchJobLifecycleService(store).reconcile(
        job.job_id,
        actor=job.actor,
        status=status,
    )

    assert result.ok is False
    assert "requires blockers" in result.errors[0]["message"]


def test_reconcile_terminal_job_requires_new_attempt() -> None:
    """A terminal ambiguous record is never rewritten in place."""
    blocker = ResearchIssue(code="outcome_unknown", message="reconcile child")
    store = _MemoryJobStore()
    job = _job(status=ResearchJobStatus.AMBIGUOUS, blockers=(blocker,), attempt=4)
    store.jobs[job.job_id] = job

    result = ResearchJobLifecycleService(store).reconcile(
        job.job_id,
        actor=job.actor,
        status=ResearchJobStatus.SUCCEEDED,
    )

    assert result.ok is False
    assert "requires a new attempt" in result.errors[0]["message"]
