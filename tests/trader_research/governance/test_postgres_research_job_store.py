"""Contracts for the durable ResearchJob Postgres projection.

Subject: Typed job persistence, idempotent admission, and append-only lifecycle
projections.
Level: Schema unit contract plus guarded Postgres adapter integration.
Collaborators: ResearchJob values and the isolated research Postgres schema; no
worker, MCP transport, model, or operation-specific execution engine.
Guarantees: A fresh store connection can reload a job, conflicting idempotency
requests fail closed, terminal state cannot be overwritten, and one worker lease
can be claimed, renewed, completed, or reconciled after expiry.
Non-goals: Command authorization, retry-attempt admission, or producer migration.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
import psycopg
from psycopg.rows import dict_row

from trader_research.governance import (
    ResearchIssue,
    ResearchJob,
    ResearchJobStatus,
    ResearchOperationKind,
    artifact_report_ref,
)
from trader_research.infrastructure.postgres import (
    PostgresResearchJobStore,
    RESEARCH_ARTIFACT_SCHEMA_STATEMENTS,
    ResearchJobConflict,
    ResearchJobTransitionError,
)


def _job(**overrides: object) -> ResearchJob:
    """Build a bounded fixture job for repository tests."""
    values: dict[str, object] = {
        "job_id": "job-persistence-1",
        "operation_kind": ResearchOperationKind.BACKTEST,
        "request_ref": "research://postgres/backtest_specification/spec-1",
        "request_digest": "sha256:request-1",
        "idempotency_key": "request-1",
        "requested_by": "objective-1",
        "actor": "workflow-executor",
        "code_identity": "git:commit-1",
        "environment_identity": "env:qualification",
    }
    values.update(overrides)
    return ResearchJob(**values)


def test_research_schema_declares_typed_job_and_transition_tables() -> None:
    """Keep the schema contract explicit before any Postgres fixture starts."""
    schema = "\n".join(RESEARCH_ARTIFACT_SCHEMA_STATEMENTS)

    assert "CREATE TABLE IF NOT EXISTS research_jobs" in schema
    assert "idempotency_key TEXT NOT NULL UNIQUE" in schema
    assert "CREATE TABLE IF NOT EXISTS research_job_transitions" in schema
    assert "REFERENCES research_jobs(job_id)" in schema


def test_job_lease_identity_round_trips_through_public_contract() -> None:
    """Lease identity remains bounded and typed without persisting hidden state."""
    original = _job(
        status=ResearchJobStatus.RUNNING,
        attempt=1,
        lease_id="lease-1",
        lease_expires_at=datetime(2026, 10, 11, 22, 0, tzinfo=timezone.utc),
        produced_artifact_refs=(artifact_report_ref("backtest_run", "run-1"),),
    )

    assert ResearchJob.from_dict(original.to_dict()) == original
    assert "prompt" not in original.to_dict()
    assert "credentials" not in original.to_dict()


@pytest.mark.postgres
def test_research_job_survives_fresh_connection_and_idempotent_replay(
    postgres_research_artifact_store,
    postgres_settings: dict[str, object],
) -> None:
    """A second connection reloads the same bounded job and exact replay is stable."""
    first = PostgresResearchJobStore(postgres_research_artifact_store.connection())
    job = first.admit(_job())

    second_connection = psycopg.connect(**postgres_settings, row_factory=dict_row)
    second_connection.autocommit = True
    try:
        second = PostgresResearchJobStore(second_connection)
        assert second.load(job.job_id) == job
        replay = _job(job_id="new-generated-id")
        assert second.admit(replay) == job
    finally:
        second_connection.close()


@pytest.mark.postgres
def test_research_job_conflicting_idempotency_and_terminal_mutation_fail_closed(
    postgres_research_artifact_store,
) -> None:
    """Request conflicts and terminal rewrites remain visible persistence errors."""
    store = PostgresResearchJobStore(postgres_research_artifact_store.connection())
    admitted = store.admit(_job())
    running = ResearchJob.from_dict(
        {
            **admitted.to_dict(),
            "status": ResearchJobStatus.RUNNING.value,
            "attempt": 1,
            "lease_id": "lease-1",
            "lease_expires_at": (
                datetime.now(timezone.utc) + timedelta(minutes=5)
            ).isoformat(),
        }
    )
    store.save(running, expected_status=ResearchJobStatus.QUEUED)

    with pytest.raises(ResearchJobConflict, match="request_digest"):
        store.admit(_job(request_digest="sha256:changed"))

    blocker = ResearchIssue(code="worker_failed", message="Worker exited.")
    terminal = ResearchJob.from_dict(
        {
            **running.to_dict(),
            "status": ResearchJobStatus.FAILED.value,
            "lease_id": None,
            "lease_expires_at": None,
            "blockers": [blocker.to_dict()],
        }
    )
    store.save(terminal, expected_status=ResearchJobStatus.RUNNING)
    with pytest.raises(ResearchJobTransitionError, match="terminal"):
        store.save(
            ResearchJob.from_dict(
                {
                    **terminal.to_dict(),
                    "status": ResearchJobStatus.RUNNING.value,
                }
            )
        )

    transitions = (
        postgres_research_artifact_store.connection()
        .execute(
            "SELECT from_status, to_status FROM research_job_transitions "
            "WHERE job_id = %s ORDER BY transition_id",
            [admitted.job_id],
        )
        .fetchall()
    )
    assert transitions == [
        {"from_status": None, "to_status": "queued"},
        {"from_status": "queued", "to_status": "running"},
        {"from_status": "running", "to_status": "failed"},
    ]


@pytest.mark.postgres
def test_worker_lease_claim_heartbeat_and_terminal_outcome_are_durable(
    postgres_research_artifact_store,
) -> None:
    """Lease ownership and typed child evidence survive the store boundary."""
    store = PostgresResearchJobStore(postgres_research_artifact_store.connection())
    store.admit(_job())

    claimed = store.claim_next(worker_id="worker-a", lease_seconds=30, max_attempts=3)
    assert claimed is not None
    assert claimed.status is ResearchJobStatus.RUNNING
    assert claimed.attempt == 1
    assert (
        store.heartbeat(
            claimed.job_id,
            worker_id="worker-a",
            lease_id=claimed.lease_id or "",
            lease_seconds=30,
        )
        is True
    )

    finished = store.finish(
        claimed.job_id,
        worker_id="worker-a",
        lease_id=claimed.lease_id or "",
        status=ResearchJobStatus.SUCCEEDED,
        produced_artifact_refs=(artifact_report_ref("backtest_run", "run-1"),),
    )
    assert finished is not None
    assert finished.status is ResearchJobStatus.SUCCEEDED
    assert store.load(claimed.job_id).produced_artifact_refs[0].artifact_id == "run-1"


@pytest.mark.postgres
def test_expired_worker_lease_requires_reconciliation_without_reclaim(
    postgres_research_artifact_store,
) -> None:
    """Worker loss becomes a terminal reconciliation state instead of a replay."""
    store = PostgresResearchJobStore(postgres_research_artifact_store.connection())
    store.admit(_job(job_id="job-expired-1", idempotency_key="expired-1"))
    claimed = store.claim_next(worker_id="worker-a", lease_seconds=30, max_attempts=3)
    assert claimed is not None
    expired = ResearchJob.from_dict(
        {
            **claimed.to_dict(),
            "lease_expires_at": (
                datetime.now(timezone.utc) - timedelta(seconds=1)
            ).isoformat(),
        }
    )
    store.save(expired, expected_status=ResearchJobStatus.RUNNING)

    recovered = store.reconcile_expired_leases()
    assert len(recovered) == 1
    assert recovered[0].status is ResearchJobStatus.RECONCILIATION_REQUIRED
    assert (
        store.claim_next(worker_id="worker-b", lease_seconds=30, max_attempts=3) is None
    )
