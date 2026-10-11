"""Retained qualification for durable research-job recovery semantics.

Subject: The TRD-321A Postgres projection and TRD-321B lifecycle commands
across every public state, idempotent admission, cancellation, lease expiry,
and uncertain provider/storage outcomes.
Level: Cross-package deterministic qualification, with a guarded Postgres
fresh-process reload when the controlled verification environment is present.
Collaborators: ``ResearchJob``, ``ResearchJobLifecycleService``,
``PostgresResearchJobStore``, and a small in-memory persistence fixture; no
worker scheduler, model, MCP transport, broker, or scientific evaluator.
Guarantees: The retained report names the exact fixture, contract, checkout,
command, assertions, and blocker states. The full state matrix and command
contract run offline; Postgres evidence is skipped when its guarded settings
are absent and never downgraded to an in-memory claim.
Non-goals: Worker scheduling, retry-attempt creation, operation-specific child
producers, model-backed acceptance, scientific validity, or live trading.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
import psycopg
from psycopg.rows import dict_row
import pytest

from trader_research.governance import (
    ResearchIssue,
    ResearchJob,
    ResearchJobLifecycleService,
    ResearchJobStatus,
    ResearchOperationKind,
    artifact_report_ref,
)
from trader_research.infrastructure.postgres import (
    PostgresResearchJobStore,
    ResearchJobConflict,
    ResearchJobNotFound,
    ResearchJobTransitionError,
)


_FIXTURE_ID = "trd-321c-research-job-recovery-v1"
_CONTRACT = "ResearchJobLifecycleService/PostgresResearchJobStore"
_QUALIFICATION_COMMAND = (
    "uv run pytest tests/cross_package/qualification/"
    "test_postgres_research_job_recovery.py -q"
)


@dataclass
class _MemoryJobStore:
    """Deterministic store fixture preserving the Postgres transition contract."""

    jobs: dict[str, ResearchJob]
    transitions: list[tuple[str | None, str, str]]

    def __init__(self) -> None:
        self.jobs = {}
        self.transitions = []

    def admit(self, job: ResearchJob) -> ResearchJob:
        """Admit a queued projection or return its exact idempotent replay."""
        existing = next(
            (
                candidate
                for candidate in self.jobs.values()
                if candidate.idempotency_key == job.idempotency_key
            ),
            None,
        )
        if existing is not None:
            self._assert_same_request(existing, job)
            return existing
        if job.job_id in self.jobs:
            raise ResearchJobConflict(f"job_id already exists: {job.job_id}")
        self.jobs[job.job_id] = job
        self.transitions.append((None, job.job_id, job.status.value))
        return job

    def load(self, job_id: str) -> ResearchJob:
        """Load one exact fixture projection."""
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
        """Apply the same transition and terminal rewrite rules as Postgres."""
        current = self.load(job.job_id)
        if expected_status is not None and current.status is not expected_status:
            raise ResearchJobTransitionError(
                f"expected {expected_status.value}, found {current.status.value}"
            )
        self._assert_same_request(current, job)
        if current == job:
            return current
        if current.terminal:
            raise ResearchJobTransitionError("terminal job cannot transition")
        allowed = {
            ResearchJobStatus.QUEUED: {
                ResearchJobStatus.RUNNING,
                ResearchJobStatus.CANCELLED,
            },
            ResearchJobStatus.RUNNING: {
                ResearchJobStatus.PARTIAL,
                ResearchJobStatus.SUCCEEDED,
                ResearchJobStatus.FAILED,
                ResearchJobStatus.CANCELLED,
                ResearchJobStatus.AMBIGUOUS,
                ResearchJobStatus.RECONCILIATION_REQUIRED,
            },
            ResearchJobStatus.PARTIAL: {
                ResearchJobStatus.RUNNING,
                ResearchJobStatus.SUCCEEDED,
                ResearchJobStatus.FAILED,
                ResearchJobStatus.CANCELLED,
                ResearchJobStatus.AMBIGUOUS,
                ResearchJobStatus.RECONCILIATION_REQUIRED,
            },
        }
        if job.status is not current.status and job.status not in allowed[current.status]:
            raise ResearchJobTransitionError(
                f"illegal job transition: {current.status.value} -> {job.status.value}"
            )
        self.jobs[job.job_id] = job
        self.transitions.append((current.status.value, job.job_id, job.status.value))
        return job

    @staticmethod
    def _assert_same_request(existing: ResearchJob, candidate: ResearchJob) -> None:
        """Reject immutable request or execution identity drift."""
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
            if getattr(existing, field) != getattr(candidate, field):
                raise ResearchJobConflict(f"research job {field} conflicts")


def _job(**overrides: object) -> ResearchJob:
    """Build one bounded queued fixture projection."""
    values: dict[str, object] = {
        "job_id": "trd-321c-job-1",
        "operation_kind": ResearchOperationKind.BACKTEST,
        "request_ref": "research://postgres/backtest_specification/trd-321c-spec-1",
        "request_digest": "sha256:trd-321c-request-1",
        "idempotency_key": "trd-321c-request-1",
        "requested_by": "trd-321c-qualification",
        "actor": "workflow-executor",
        "code_identity": "git:trd-321c-fixture",
        "environment_identity": "env:trd-321c-controlled",
    }
    values.update(overrides)
    return ResearchJob(**values)


def _running(job: ResearchJob, *, attempt: int = 1, expired: bool = False) -> ResearchJob:
    """Create a worker-owned running projection with an optional expired lease."""
    now = datetime.now(timezone.utc)
    return replace(
        job,
        status=ResearchJobStatus.RUNNING,
        attempt=attempt,
        lease_id=f"trd-321c-lease-{attempt}",
        lease_expires_at=now - timedelta(minutes=1)
        if expired
        else now + timedelta(minutes=5),
    )


def _blocker(code: str, message: str, **details: object) -> ResearchIssue:
    """Build one explicit retained blocker."""
    return ResearchIssue(code=code, message=message, details=details)


def _transition_to_running(
    store: _MemoryJobStore, service: ResearchJobLifecycleService, job: ResearchJob
) -> ResearchJob:
    """Admit then claim one fixture job for a deterministic scenario."""
    admitted = service.submit(job)
    assert admitted.ok is True
    return store.save(_running(job), expected_status=ResearchJobStatus.QUEUED)


def test_trd321c_recovery_campaign_retains_report(tmp_path: Path) -> None:
    """Qualify the full state matrix and retain credential-free JSON evidence."""
    store = _MemoryJobStore()
    service = ResearchJobLifecycleService(store)

    queued_job = _job()
    queued = service.submit(queued_job)
    assert queued.ok is True
    replay = service.submit(replace(queued_job, job_id="trd-321c-generated-replay"))
    assert replay.ok is True
    assert replay.data == queued.data
    conflict = service.submit(
        replace(queued_job, job_id="trd-321c-conflicting", request_digest="sha256:changed")
    )
    assert conflict.ok is False
    assert conflict.errors[0]["code"] == "research_job_submission_failed"

    child = artifact_report_ref("backtest_run", "trd-321c-child-run")
    evaluation = artifact_report_ref("evaluation_report", "trd-321c-child-evaluation")
    warning = ResearchIssue(code="slow_worker", message="worker exceeded fixture budget")
    partial_blocker = _blocker(
        "child_artifact_partial", "one child artifact remains unresolved", child=child.uri
    )
    partial_job = _job(job_id="trd-321c-partial", idempotency_key="trd-321c-partial-key")
    _transition_to_running(store, service, partial_job)
    partial = service.reconcile(
        partial_job.job_id,
        actor=partial_job.actor,
        status=ResearchJobStatus.PARTIAL,
        produced_artifact_refs=(child,),
        warnings=(warning,),
        blockers=(partial_blocker,),
    )
    assert partial.ok is True
    succeeded = service.reconcile(
        partial_job.job_id,
        actor=partial_job.actor,
        status=ResearchJobStatus.SUCCEEDED,
        produced_artifact_refs=(child, evaluation),
    )
    assert succeeded.ok is True
    succeeded_projection = ResearchJob.from_dict(succeeded.data["research_job"])
    assert succeeded_projection.status is ResearchJobStatus.SUCCEEDED
    assert [ref.uri for ref in succeeded_projection.produced_artifact_refs] == [
        child.uri,
        evaluation.uri,
    ]

    failed_job = _job(job_id="trd-321c-failed", idempotency_key="trd-321c-failed-key")
    _transition_to_running(store, service, failed_job)
    failed = service.reconcile(
        failed_job.job_id,
        actor=failed_job.actor,
        status=ResearchJobStatus.FAILED,
        blockers=(_blocker("worker_failed", "fixture worker exited"),),
    )
    assert failed.ok is True
    assert ResearchJob.from_dict(failed.data["research_job"]).status is ResearchJobStatus.FAILED

    cancelled_job = _job(job_id="trd-321c-cancelled", idempotency_key="trd-321c-cancelled-key")
    _transition_to_running(store, service, cancelled_job)
    cancelled = service.cancel(cancelled_job.job_id, actor=cancelled_job.actor, reason="operator stop")
    assert cancelled.ok is True
    cancelled_replay = service.cancel(
        cancelled_job.job_id, actor=cancelled_job.actor, reason="operator stop"
    )
    assert cancelled_replay.data == cancelled.data
    cancelled_projection = ResearchJob.from_dict(cancelled.data["research_job"])
    assert cancelled_projection.status is ResearchJobStatus.CANCELLED
    assert cancelled_projection.lease_id is None
    assert cancelled_projection.blockers[-1].code == "operator_cancelled"

    ambiguous_job = _job(job_id="trd-321c-ambiguous", idempotency_key="trd-321c-ambiguous-key")
    _transition_to_running(store, service, ambiguous_job)
    ambiguous = service.reconcile(
        ambiguous_job.job_id,
        actor=ambiguous_job.actor,
        status=ResearchJobStatus.AMBIGUOUS,
        blockers=(_blocker("provider_terminal_unknown", "provider response was lost"),),
    )
    assert ambiguous.ok is True
    assert ResearchJob.from_dict(ambiguous.data["research_job"]).retryable is False
    assert service.reconcile(
        ambiguous_job.job_id,
        actor=ambiguous_job.actor,
        status=ResearchJobStatus.AMBIGUOUS,
    ).data == ambiguous.data

    expired_job = _job(job_id="trd-321c-expired", idempotency_key="trd-321c-expired-key")
    service.submit(expired_job)
    store.save(_running(expired_job, expired=True), expected_status=ResearchJobStatus.QUEUED)
    expired = service.reconcile(
        expired_job.job_id,
        actor=expired_job.actor,
        status=ResearchJobStatus.RECONCILIATION_REQUIRED,
        blockers=(
            _blocker(
                "worker_lease_expired",
                "worker lease expired before a terminal receipt",
                lease_id="trd-321c-lease-1",
            ),
        ),
    )
    assert expired.ok is True
    expired_projection = ResearchJob.from_dict(expired.data["research_job"])
    assert expired_projection.status is ResearchJobStatus.RECONCILIATION_REQUIRED
    assert expired_projection.lease_id is None

    storage_loss_job = _job(job_id="trd-321c-storage-loss", idempotency_key="trd-321c-storage-loss-key")
    _transition_to_running(store, service, storage_loss_job)
    storage_loss = service.reconcile(
        storage_loss_job.job_id,
        actor=storage_loss_job.actor,
        status=ResearchJobStatus.RECONCILIATION_REQUIRED,
        blockers=(_blocker("postgres_unavailable", "durable receipt could not be read"),),
    )
    assert storage_loss.ok is True
    provider_loss_job = _job(job_id="trd-321c-provider-loss", idempotency_key="trd-321c-provider-loss-key")
    _transition_to_running(store, service, provider_loss_job)
    provider_loss = service.reconcile(
        provider_loss_job.job_id,
        actor=provider_loss_job.actor,
        status=ResearchJobStatus.AMBIGUOUS,
        blockers=(_blocker("provider_terminal_unknown", "provider outcome is unknown"),),
    )
    assert provider_loss.ok is True

    observed_states = {
        transition[2] for transition in store.transitions
    }
    assert observed_states == {status.value for status in ResearchJobStatus}

    checkout_commit = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=Path(__file__).resolve().parents[3],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    report = {
        "fixture_id": _FIXTURE_ID,
        "contract": _CONTRACT,
        "contract_version": "1",
        "checkout_commit": checkout_commit,
        "evidence_revision": 1,
        "command": _QUALIFICATION_COMMAND,
        "assertions": {
            "state_matrix": sorted(observed_states),
            "duplicate_submission": "exact replay passed; conflicting request rejected",
            "fresh_process_recovery": "guarded Postgres campaign below; skipped when env absent",
            "cancellation": "terminal, lease cleared, actor and reason retained",
            "partial_child_artifacts": "refs retained through partial to succeeded",
            "storage_and_provider_loss": "explicit blocker states require reconciliation",
        },
        "blocker_states": {
            "worker_lease_expired": "reconciliation_required",
            "postgres_unavailable": "reconciliation_required",
            "provider_terminal_unknown": "ambiguous",
            "model_or_scientific_acceptance": "not_claimed",
        },
        "verdict": (
            "deterministic durable ResearchJob command contract qualified; "
            "model-backed and scientific acceptance not claimed"
        ),
    }
    report_path = tmp_path / f"{_FIXTURE_ID}.json"
    report_path.write_text(json.dumps(report, sort_keys=True, indent=2), encoding="utf-8")
    retained = json.loads(report_path.read_text(encoding="utf-8"))
    assert retained["fixture_id"] == _FIXTURE_ID
    assert retained["contract"] == _CONTRACT
    assert retained["checkout_commit"] == checkout_commit
    assert retained["command"] == _QUALIFICATION_COMMAND
    assert retained["blocker_states"]["model_or_scientific_acceptance"] == "not_claimed"


@pytest.mark.postgres
def test_trd321c_postgres_fresh_process_reload_and_terminal_recovery(
    postgres_research_artifact_store,
    postgres_settings: dict[str, object],
) -> None:
    """Prove an independent Python process reloads and reconciles one job."""
    first_store = PostgresResearchJobStore(postgres_research_artifact_store.connection())
    service = ResearchJobLifecycleService(first_store)
    job = _job(job_id="trd-321c-postgres-reload", idempotency_key="trd-321c-postgres-reload-key")
    assert service.submit(job).ok is True
    running = replace(
        job,
        status=ResearchJobStatus.RUNNING,
        attempt=1,
        lease_id="trd-321c-postgres-lease",
        lease_expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
    )
    first_store.save(running, expected_status=ResearchJobStatus.QUEUED)

    script = """
import json
import os
import psycopg
from psycopg.rows import dict_row
from trader_research.infrastructure.postgres import PostgresResearchJobStore

settings = json.loads(os.environ["TRD321C_POSTGRES_SETTINGS"])
with psycopg.connect(**settings, row_factory=dict_row) as connection:
    connection.autocommit = True
    projection = PostgresResearchJobStore(connection).load("trd-321c-postgres-reload")
    print(json.dumps(projection.to_dict(), sort_keys=True))
"""
    environment = os.environ.copy()
    environment["TRD321C_POSTGRES_SETTINGS"] = json.dumps(postgres_settings)
    fresh = subprocess.run(
        [sys.executable, "-c", script],
        check=True,
        capture_output=True,
        text=True,
        env=environment,
    )
    projection = json.loads(fresh.stdout)
    assert projection["status"] == ResearchJobStatus.RUNNING.value
    assert projection["attempt"] == 1
    assert projection["lease_id"] == running.lease_id

    reconciled = ResearchJobLifecycleService(first_store).reconcile(
        job.job_id,
        actor=job.actor,
        status=ResearchJobStatus.SUCCEEDED,
        produced_artifact_refs=(artifact_report_ref("backtest_run", "trd-321c-postgres-run"),),
    )
    assert reconciled.ok is True
    with psycopg.connect(**postgres_settings, row_factory=dict_row) as connection:
        connection.autocommit = True
        recovered = PostgresResearchJobStore(connection).load(job.job_id)
    assert recovered.status is ResearchJobStatus.SUCCEEDED
    assert recovered.produced_artifact_refs[0].artifact_id == "trd-321c-postgres-run"
