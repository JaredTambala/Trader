"""ResearchJob worker contracts over a durable lease-capable store double.

Subject: Approved backtest claim, lease renewal, terminal outcome retention, and
worker-loss ambiguity handling.
Level: Worker unit contracts.
Collaborators: Typed ResearchJob, an in-memory lease store, and injected
BacktestRunner adapter; no Postgres, MCP transport, or broker.
Guarantees: A claimed backtest is executed once per lease, progress renews the
lease, producer outcomes remain explicit, and lost ownership cannot be reported
as success.
Non-goals: SQL locking, canonical result construction, provider credentials, or
strategy performance claims.
"""

from __future__ import annotations

import asyncio
from dataclasses import replace
from datetime import UTC, datetime

import pytest

from trader_console_api.worker import (
    AmbiguousExecutionError,
    ResearchJobExecutionOutcome,
    ResearchJobWorker,
    deterministic_research_run_id,
)
from trader_research.governance import (
    ResearchIssue,
    ResearchJob,
    ResearchJobStatus,
    ResearchOperationKind,
    artifact_report_ref,
)


def _job() -> ResearchJob:
    """Build one admitted approved backtest job."""
    return ResearchJob(
        job_id="research-job-worker-1",
        operation_kind=ResearchOperationKind.BACKTEST,
        request_ref="research://postgres/experiment_job_request/request-1",
        request_digest="sha256:request-1",
        idempotency_key="request-1",
        requested_by="workflow-1",
        actor="workflow_executor",
        code_identity="git:approved",
        environment_identity="env:test",
    )


class _Store:
    """Lease-capable store double with explicit terminal transition history."""

    def __init__(self, job: ResearchJob) -> None:
        self.job = job
        self.calls: list[str] = []
        self.heartbeat_ok = True

    def claim_next(
        self, *, worker_id: str, lease_seconds: int, max_attempts: int
    ) -> ResearchJob | None:
        """Claim the queued fixture once."""
        self.calls.append("claim")
        if self.job.status is not ResearchJobStatus.QUEUED:
            return None
        claimed = replace(
            self.job,
            status=ResearchJobStatus.RUNNING,
            attempt=1,
            lease_id=f"{worker_id}:lease-1",
            lease_expires_at=datetime.now(UTC),
        )
        self.job = claimed
        return claimed

    def heartbeat(
        self, job_id: str, *, worker_id: str, lease_id: str, lease_seconds: int
    ) -> bool:
        """Record a lease renewal and return configured ownership state."""
        self.calls.append("heartbeat")
        return self.heartbeat_ok

    def finish(
        self,
        job_id: str,
        *,
        worker_id: str,
        lease_id: str,
        status: ResearchJobStatus,
        produced_artifact_refs=(),
        warnings=(),
        blockers=(),
        retryable=False,
    ):
        """Persist the bounded terminal projection exactly once."""
        self.calls.append(f"finish:{status.value}")
        if self.job.status not in {
            ResearchJobStatus.RUNNING,
            ResearchJobStatus.PARTIAL,
        }:
            return None
        self.job = replace(
            self.job,
            status=status,
            lease_id=None,
            lease_expires_at=None,
            produced_artifact_refs=tuple(produced_artifact_refs),
            warnings=tuple(warnings),
            blockers=tuple(blockers),
            retryable=retryable,
        )
        return self.job


class _Executor:
    """Injected adapter standing in for the canonical BacktestRunner."""

    def __init__(self, outcome: ResearchJobExecutionOutcome) -> None:
        self.outcome = outcome
        self.run_ids: list[str] = []

    async def execute(self, job, *, run_id, progress):
        """Renew the job lease before returning the configured outcome."""
        self.run_ids.append(run_id)
        await progress(datetime(2026, 1, 1, tzinfo=UTC))
        return self.outcome


class _AmbiguousExecutor:
    """Adapter that cannot prove whether producer evidence was committed."""

    async def execute(self, job, *, run_id, progress):
        """Raise the explicit worker ambiguity signal."""
        del run_id
        raise AmbiguousExecutionError("BacktestRunner result connection was lost")


def test_research_worker_renews_and_persists_success_once() -> None:
    """A claimed backtest retains its produced artifact and terminal success."""
    store = _Store(_job())
    executor = _Executor(
        ResearchJobExecutionOutcome(
            status="succeeded",
            produced_artifact_refs=(artifact_report_ref("backtest_run", "run-1"),),
        )
    )
    worker = ResearchJobWorker(
        store,
        executor,
        worker_id="worker-a",
    )

    assert asyncio.run(worker.run_once()) is True
    assert store.calls == ["claim", "heartbeat", "finish:succeeded"]
    assert store.job.status is ResearchJobStatus.SUCCEEDED
    assert store.job.produced_artifact_refs[0].artifact_id == "run-1"
    assert executor.run_ids == [
        deterministic_research_run_id(store.job.job_id, store.job.request_digest)
    ]


@pytest.mark.parametrize("status", ["partial", "failed"])
def test_research_worker_preserves_non_success_outcomes(status: str) -> None:
    """Partial and failed producer outcomes retain their blockers and status."""
    blocker = ResearchIssue(code="producer", message="bounded producer outcome")
    store = _Store(_job())
    worker = ResearchJobWorker(
        store,
        _Executor(ResearchJobExecutionOutcome(status=status, blockers=(blocker,))),
        worker_id="worker-a",
    )

    assert asyncio.run(worker.run_once()) is True
    assert store.job.status.value == status
    assert store.job.blockers == (blocker,)


def test_research_worker_marks_ambiguous_producer_for_reconciliation() -> None:
    """A producer connection loss never becomes a retryable success or failure."""
    store = _Store(_job())
    worker = ResearchJobWorker(store, _AmbiguousExecutor(), worker_id="worker-a")

    assert asyncio.run(worker.run_once()) is True
    assert store.job.status is ResearchJobStatus.RECONCILIATION_REQUIRED
    assert store.job.retryable is False


def test_research_worker_refuses_success_after_losing_lease() -> None:
    """A lost progress lease forces reconciliation before terminal persistence."""
    store = _Store(_job())
    store.heartbeat_ok = False
    worker = ResearchJobWorker(
        store,
        _Executor(ResearchJobExecutionOutcome(status="succeeded")),
        worker_id="worker-a",
    )

    assert asyncio.run(worker.run_once()) is True
    assert store.job.status is ResearchJobStatus.RECONCILIATION_REQUIRED
    assert "finish:succeeded" not in store.calls
