"""Persist the bounded ``ResearchJob`` lifecycle projection in Postgres.

This adapter owns operational state only.  It stores the typed identity and
bounded outcome fields needed to inspect a job after a process restart.  Worker
leases, command authorization, and reconciliation policy are application
services built on top of this store in later slices.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

from trader_research.governance.orchestration.operations import (
    ResearchJob,
    ResearchJobStatus,
)
from trader_research.governance.handoffs import ArtifactReportRef, ResearchIssue

from .artifact_store import Jsonb


class ResearchJobStoreError(RuntimeError):
    """Base error for durable research-job persistence failures."""


class ResearchJobNotFound(ResearchJobStoreError):
    """Raised when a requested job identity is absent."""


class ResearchJobConflict(ResearchJobStoreError):
    """Raised when an idempotency or immutable identity conflicts."""


class ResearchJobTransitionError(ResearchJobStoreError):
    """Raised when a job update would violate the lifecycle contract."""


_ALLOWED_TRANSITIONS: dict[ResearchJobStatus, frozenset[ResearchJobStatus]] = {
    ResearchJobStatus.QUEUED: frozenset(
        {ResearchJobStatus.RUNNING, ResearchJobStatus.CANCELLED}
    ),
    ResearchJobStatus.RUNNING: frozenset(
        {
            ResearchJobStatus.PARTIAL,
            ResearchJobStatus.SUCCEEDED,
            ResearchJobStatus.FAILED,
            ResearchJobStatus.CANCELLED,
            ResearchJobStatus.AMBIGUOUS,
            ResearchJobStatus.RECONCILIATION_REQUIRED,
        }
    ),
    ResearchJobStatus.PARTIAL: frozenset(
        {
            ResearchJobStatus.RUNNING,
            ResearchJobStatus.SUCCEEDED,
            ResearchJobStatus.FAILED,
            ResearchJobStatus.CANCELLED,
            ResearchJobStatus.AMBIGUOUS,
            ResearchJobStatus.RECONCILIATION_REQUIRED,
        }
    ),
    ResearchJobStatus.SUCCEEDED: frozenset(),
    ResearchJobStatus.FAILED: frozenset(),
    ResearchJobStatus.CANCELLED: frozenset(),
    ResearchJobStatus.AMBIGUOUS: frozenset(),
    ResearchJobStatus.RECONCILIATION_REQUIRED: frozenset(),
}


class PostgresResearchJobStore:
    """Persist and reload one typed research-job projection.

    The caller supplies an already configured Postgres connection owned by the
    research infrastructure composition.  ``admit`` is idempotent by
    ``idempotency_key``; ``save`` appends a transition row and rejects terminal
    mutation or immutable identity changes.
    """

    def __init__(self, connection: Any) -> None:
        """Bind the store to a configured Postgres connection."""
        self._connection = connection

    def admit(self, job: ResearchJob) -> ResearchJob:
        """Persist a queued job or return the exact request's current state.

        A repeated idempotency key with a different immutable request fails
        closed.  Admission never accepts a pre-running or terminal projection.
        """
        if job.status is not ResearchJobStatus.QUEUED:
            raise ResearchJobTransitionError("job admission requires queued status")
        if job.attempt != 0 or job.lease_id is not None:
            raise ResearchJobTransitionError(
                "job admission requires attempt 0 without a lease"
            )
        with self._connection.transaction():
            existing = self._load_by_idempotency(job.idempotency_key, lock=True)
            if existing is not None:
                self._assert_same_request(existing, job)
                return existing
            if self._load_row(job.job_id, lock=True) is not None:
                raise ResearchJobConflict(f"job_id already exists: {job.job_id}")
            self._insert_job(job)
            self._insert_transition(None, job)
        return job

    def load(self, job_id: str) -> ResearchJob:
        """Load one bounded job projection by exact ID."""
        row = self._load_row(job_id)
        if row is None:
            raise ResearchJobNotFound(f"unknown research job: {job_id}")
        return _job_from_row(row)

    def save(
        self,
        job: ResearchJob,
        *,
        expected_status: ResearchJobStatus | None = None,
    ) -> ResearchJob:
        """Persist an allowed non-terminal update and append its transition.

        Immutable request and execution identities cannot change in place.  A
        terminal record is append-only; retries require a new attempt record in
        a later service slice after reconciliation.
        """
        with self._connection.transaction():
            current_row = self._load_row(job.job_id, lock=True)
            if current_row is None:
                raise ResearchJobNotFound(f"unknown research job: {job.job_id}")
            current = _job_from_row(current_row)
            if expected_status is not None and current.status is not expected_status:
                raise ResearchJobTransitionError(
                    f"expected {expected_status.value}, found {current.status.value}"
                )
            self._assert_same_request(current, job)
            if current == job:
                return current
            if current.terminal:
                raise ResearchJobTransitionError(
                    f"terminal job {job.job_id} cannot transition"
                )
            if (
                job.status is not current.status
                and job.status not in _ALLOWED_TRANSITIONS[current.status]
            ):
                raise ResearchJobTransitionError(
                    f"illegal job transition: {current.status.value} -> {job.status.value}"
                )
            self._update_job(job)
            self._insert_transition(current.status, job)
        return job

    def claim_next(
        self,
        *,
        worker_id: str,
        lease_seconds: int,
        max_attempts: int,
    ) -> ResearchJob | None:
        """Atomically claim one queued job with a bounded lease.

        Expired leased jobs are never replayed by this method. A separate
        reconciliation pass must classify them before a new attempt can be
        admitted, which prevents duplicate producer evidence after worker loss.
        """
        _validate_worker_parameters(worker_id, lease_seconds, max_attempts)
        with self._connection.transaction():
            row = self._connection.execute(
                _SELECT_JOB + " WHERE status = 'queued' AND attempt < %s "
                "ORDER BY created_at, job_id FOR UPDATE SKIP LOCKED LIMIT 1",
                [max_attempts],
            ).fetchone()
            if row is None:
                return None
            current = _job_from_row(row)
            now = datetime.now(UTC)
            claimed = replace(
                current,
                status=ResearchJobStatus.RUNNING,
                attempt=current.attempt + 1,
                lease_id=f"{worker_id}:{uuid4().hex}",
                lease_expires_at=now + timedelta(seconds=lease_seconds),
            )
            self._update_job(claimed)
            self._insert_transition(current.status, claimed)
            return claimed

    def heartbeat(
        self,
        job_id: str,
        *,
        worker_id: str,
        lease_id: str,
        lease_seconds: int,
    ) -> bool:
        """Renew an active worker lease without changing public job status."""
        _validate_worker_parameters(worker_id, lease_seconds, 1)
        with self._connection.transaction():
            row = self._load_row(job_id, lock=True)
            if row is None:
                return False
            current = _job_from_row(row)
            if not _lease_matches(current, worker_id=worker_id, lease_id=lease_id):
                return False
            renewed = replace(
                current,
                lease_expires_at=datetime.now(UTC) + timedelta(seconds=lease_seconds),
            )
            self._update_job(renewed)
            return True

    def finish(
        self,
        job_id: str,
        *,
        worker_id: str,
        lease_id: str,
        status: ResearchJobStatus,
        produced_artifact_refs: Sequence[ArtifactReportRef] = (),
        warnings: Sequence[ResearchIssue] = (),
        blockers: Sequence[ResearchIssue] = (),
        retryable: bool = False,
    ) -> ResearchJob | None:
        """Persist one terminal or partial outcome owned by the active lease."""
        _validate_worker_parameters(worker_id, 1, 1)
        if status in {ResearchJobStatus.QUEUED, ResearchJobStatus.RUNNING}:
            raise ResearchJobTransitionError("worker finish requires an outcome status")
        with self._connection.transaction():
            row = self._load_row(job_id, lock=True)
            if row is None:
                return None
            current = _job_from_row(row)
            if not _lease_matches(current, worker_id=worker_id, lease_id=lease_id):
                return None
            completed = replace(
                current,
                status=status,
                lease_id=None,
                lease_expires_at=None,
                produced_artifact_refs=tuple(produced_artifact_refs),
                warnings=tuple(warnings),
                blockers=tuple(blockers),
                retryable=retryable,
            )
            self._update_job(completed)
            self._insert_transition(current.status, completed)
            return completed

    def reconcile_expired_leases(self) -> tuple[ResearchJob, ...]:
        """Classify expired running leases without replaying their producers."""
        reconciled: list[ResearchJob] = []
        with self._connection.transaction():
            rows = self._connection.execute(
                _SELECT_JOB + " WHERE status IN ('running', 'partial') "
                "AND lease_expires_at IS NOT NULL AND lease_expires_at <= now() "
                "ORDER BY updated_at, job_id FOR UPDATE SKIP LOCKED"
            ).fetchall()
            for row in rows:
                current = _job_from_row(row)
                blocker = ResearchIssue(
                    code="worker_lease_expired",
                    message="The worker lease expired before a terminal receipt was retained.",
                    details={"job_id": current.job_id},
                )
                expired = replace(
                    current,
                    status=ResearchJobStatus.RECONCILIATION_REQUIRED,
                    lease_id=None,
                    lease_expires_at=None,
                    blockers=(*current.blockers, blocker),
                    retryable=False,
                )
                self._update_job(expired)
                self._insert_transition(current.status, expired)
                reconciled.append(expired)
        return tuple(reconciled)

    def _load_by_idempotency(
        self, idempotency_key: str, *, lock: bool = False
    ) -> ResearchJob | None:
        row = self._connection.execute(
            _SELECT_JOB
            + " WHERE idempotency_key = %s"
            + (" FOR UPDATE" if lock else ""),
            [idempotency_key],
        ).fetchone()
        return _job_from_row(row) if row is not None else None

    def _load_row(self, job_id: str, *, lock: bool = False) -> Mapping[str, Any] | None:
        return self._connection.execute(
            _SELECT_JOB + " WHERE job_id = %s" + (" FOR UPDATE" if lock else ""),
            [job_id],
        ).fetchone()

    def _insert_job(self, job: ResearchJob) -> None:
        self._connection.execute(
            """
            INSERT INTO research_jobs (
                job_id, operation_kind, request_ref, request_digest,
                idempotency_key, requested_by, actor, code_identity,
                environment_identity, status, attempt, lease_id,
                lease_expires_at, produced_artifact_refs, warnings, blockers,
                retryable
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            _job_parameters(job),
        )

    def _update_job(self, job: ResearchJob) -> None:
        self._connection.execute(
            """
            UPDATE research_jobs
            SET status = %s,
                attempt = %s,
                lease_id = %s,
                lease_expires_at = %s,
                produced_artifact_refs = %s,
                warnings = %s,
                blockers = %s,
                retryable = %s,
                updated_at = now()
            WHERE job_id = %s
            """,
            [
                job.status.value,
                job.attempt,
                job.lease_id,
                job.lease_expires_at,
                _json([item.to_dict() for item in job.produced_artifact_refs]),
                _json([item.to_dict() for item in job.warnings]),
                _json([item.to_dict() for item in job.blockers]),
                job.retryable,
                job.job_id,
            ],
        )

    def _insert_transition(
        self, from_status: ResearchJobStatus | None, job: ResearchJob
    ) -> None:
        self._connection.execute(
            """
            INSERT INTO research_job_transitions (
                job_id, from_status, to_status, attempt, lease_id,
                lease_expires_at, produced_artifact_refs, warnings, blockers,
                retryable
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            [
                job.job_id,
                from_status.value if from_status is not None else None,
                job.status.value,
                job.attempt,
                job.lease_id,
                job.lease_expires_at,
                _json([item.to_dict() for item in job.produced_artifact_refs]),
                _json([item.to_dict() for item in job.warnings]),
                _json([item.to_dict() for item in job.blockers]),
                job.retryable,
            ],
        )

    @staticmethod
    def _assert_same_request(existing: ResearchJob, candidate: ResearchJob) -> None:
        """Reject changes to fields that identify the admitted request."""
        identity = (
            "operation_kind",
            "request_ref",
            "request_digest",
            "idempotency_key",
            "requested_by",
            "actor",
            "code_identity",
            "environment_identity",
        )
        for field in identity:
            if getattr(existing, field) != getattr(candidate, field):
                raise ResearchJobConflict(
                    f"research job {field} conflicts with the admitted request"
                )


_SELECT_JOB = """
    SELECT job_id, operation_kind, request_ref, request_digest,
           idempotency_key, requested_by, actor, code_identity,
           environment_identity, status, attempt, lease_id,
           lease_expires_at, produced_artifact_refs, warnings, blockers,
           retryable
    FROM research_jobs
"""


def _job_parameters(job: ResearchJob) -> list[Any]:
    """Return typed SQL parameters for the bounded job projection."""
    return [
        job.job_id,
        job.operation_kind.value,
        job.request_ref,
        job.request_digest,
        job.idempotency_key,
        job.requested_by,
        job.actor,
        job.code_identity,
        job.environment_identity,
        job.status.value,
        job.attempt,
        job.lease_id,
        job.lease_expires_at,
        _json([item.to_dict() for item in job.produced_artifact_refs]),
        _json([item.to_dict() for item in job.warnings]),
        _json([item.to_dict() for item in job.blockers]),
        job.retryable,
    ]


def _job_from_row(row: Mapping[str, Any]) -> ResearchJob:
    """Normalize one Postgres row into the canonical public value object."""
    return ResearchJob.from_dict(
        {
            "job_id": row["job_id"],
            "operation_kind": row["operation_kind"],
            "request_ref": row["request_ref"],
            "request_digest": row["request_digest"],
            "idempotency_key": row["idempotency_key"],
            "requested_by": row["requested_by"],
            "actor": row["actor"],
            "code_identity": row["code_identity"],
            "environment_identity": row["environment_identity"],
            "status": row["status"],
            "attempt": row["attempt"],
            "lease_id": row["lease_id"],
            "lease_expires_at": row["lease_expires_at"],
            "produced_artifact_refs": row["produced_artifact_refs"],
            "warnings": row["warnings"],
            "blockers": row["blockers"],
            "retryable": row["retryable"],
        }
    )


def _json(value: Any) -> Any:
    """Wrap JSON values for psycopg while retaining adapter-test portability."""
    return Jsonb(value) if Jsonb is not None else value


def _validate_worker_parameters(
    worker_id: str, lease_seconds: int, max_attempts: int
) -> None:
    """Validate bounded worker inputs before opening a database transaction."""
    if not worker_id.strip():
        raise ValueError("worker_id must not be blank")
    if lease_seconds < 1:
        raise ValueError("lease_seconds must be positive")
    if max_attempts < 1:
        raise ValueError("max_attempts must be positive")


def _lease_matches(job: ResearchJob, *, worker_id: str, lease_id: str) -> bool:
    """Return whether the active lease belongs to the expected worker."""
    if job.status not in {ResearchJobStatus.RUNNING, ResearchJobStatus.PARTIAL}:
        return False
    if job.lease_id != lease_id or not lease_id.startswith(f"{worker_id}:"):
        return False
    return job.lease_expires_at is not None and job.lease_expires_at > datetime.now(UTC)


__all__ = [
    "PostgresResearchJobStore",
    "ResearchJobConflict",
    "ResearchJobNotFound",
    "ResearchJobStoreError",
    "ResearchJobTransitionError",
]
