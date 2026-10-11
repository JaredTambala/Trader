"""Apply deterministic commands to the persisted research-job projection.

The lifecycle service is deliberately small.  It owns command validation and
authority checks around :class:`ResearchJob`; ``PostgresResearchJobStore`` owns
transactions, idempotent admission, and append-only transition persistence.
Worker scheduling, leases, producer-specific execution, and external provider
reconciliation remain outside this boundary.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace
from typing import Protocol

from trader_research.foundation import ApplicationResult, error_result, success_result

from ..handoffs import ArtifactReportRef, ResearchIssue
from .operations import ResearchJob, ResearchJobStatus


RESEARCH_SUBMIT_JOB = "research_submit_job"
RESEARCH_GET_JOB = "research_get_job"
RESEARCH_CANCEL_JOB = "research_cancel_job"
RESEARCH_RECONCILE_JOB = "research_reconcile_job"


class ResearchJobStore(Protocol):
    """Persistence surface required by the deterministic lifecycle service."""

    def admit(self, job: ResearchJob) -> ResearchJob:
        """Admit a queued job or return the exact idempotent replay."""

    def load(self, job_id: str) -> ResearchJob:
        """Load one job by its stable identity."""

    def save(
        self,
        job: ResearchJob,
        *,
        expected_status: ResearchJobStatus | None = None,
    ) -> ResearchJob:
        """Save one allowed lifecycle transition."""


class ResearchJobLifecycleService:
    """Validate and apply bounded submit/status/cancel/reconcile commands.

    The service never constructs a worker, retries a provider operation, or
    rewrites immutable request identity.  The actor that submitted a job or
    the requester named by the job is the only principal accepted for lifecycle
    commands in this slice; richer operator policy belongs at the application
    boundary that calls this service.
    """

    def __init__(self, store: ResearchJobStore) -> None:
        """Bind the service to a configured durable job store."""
        self._store = store

    def submit(self, job: ResearchJob) -> ApplicationResult:
        """Admit one queued job and return the bounded public projection."""
        command = RESEARCH_SUBMIT_JOB
        try:
            if job.status is not ResearchJobStatus.QUEUED:
                raise ValueError("job submission requires queued status")
            admitted = self._store.admit(job)
        except (RuntimeError, ValueError, TypeError) as exc:
            return _error(command, "research_job_submission_failed", str(exc))
        return _success(command, admitted)

    def status(self, job_id: str) -> ApplicationResult:
        """Read one exact persisted public projection without recomputation."""
        command = RESEARCH_GET_JOB
        try:
            normalized_id = _required_text(job_id, "job_id")
            job = self._store.load(normalized_id)
        except (RuntimeError, ValueError, TypeError) as exc:
            return _error(command, "research_job_status_failed", str(exc))
        return _success(command, job)

    def cancel(self, job_id: str, *, actor: str, reason: str) -> ApplicationResult:
        """Cancel a queued, running, or partial job with an audited blocker.

        Existing actor, attempt, child refs, warnings, and blockers are copied
        into the terminal projection.  Repeating the same cancellation is an
        idempotent status read; a different principal is rejected even when the
        job is already cancelled.
        """
        command = RESEARCH_CANCEL_JOB
        try:
            normalized_actor = _required_text(actor, "actor")
            normalized_reason = _required_text(reason, "reason")
            job = self._store.load(_required_text(job_id, "job_id"))
            _authorize(job, normalized_actor)
            if job.status is ResearchJobStatus.CANCELLED:
                _assert_same_cancellation(job, normalized_actor, normalized_reason)
                return _success(command, job)
            if job.terminal:
                raise ValueError(
                    f"terminal research job {job.job_id} cannot be cancelled"
                )
            cancellation = ResearchIssue(
                code="operator_cancelled",
                message=normalized_reason,
                details={"actor": normalized_actor},
            )
            cancelled = replace(
                job,
                status=ResearchJobStatus.CANCELLED,
                lease_id=None,
                lease_expires_at=None,
                blockers=(*job.blockers, cancellation),
                retryable=False,
            )
            saved = self._store.save(cancelled, expected_status=job.status)
        except (RuntimeError, ValueError, TypeError) as exc:
            return _error(command, "research_job_cancellation_failed", str(exc))
        return _success(command, saved)

    def reconcile(
        self,
        job_id: str,
        *,
        actor: str,
        status: ResearchJobStatus,
        produced_artifact_refs: Sequence[ArtifactReportRef] | None = None,
        warnings: Sequence[ResearchIssue] | None = None,
        blockers: Sequence[ResearchIssue] | None = None,
        retryable: bool = False,
    ) -> ApplicationResult:
        """Record a canonical outcome discovered after an uncertain operation.

        Reconciliation preserves immutable identity, submitting actor, attempt,
        and all previously retained child refs/blockers.  New refs and issues
        are appended without duplication.  A terminal ambiguous record cannot
        be rewritten by this service; callers must create a separately modelled
        retry attempt after the worker or provider has proved that no accepted
        side effect will be duplicated.
        """
        command = RESEARCH_RECONCILE_JOB
        try:
            normalized_actor = _required_text(actor, "actor")
            job = self._store.load(_required_text(job_id, "job_id"))
            _authorize(job, normalized_actor)
            if not isinstance(status, ResearchJobStatus):
                status = ResearchJobStatus(str(status))
            if job.terminal:
                if job.status is status:
                    return _success(command, job)
                raise ValueError(
                    f"terminal research job {job.job_id} requires a new attempt"
                )
            if status is ResearchJobStatus.QUEUED:
                raise ValueError("reconciliation cannot return a job to queued")
            if status is ResearchJobStatus.RUNNING and job.status is ResearchJobStatus.QUEUED:
                raise ValueError("reconciliation cannot claim a queued job")
            retained_refs = _append_unique_refs(
                job.produced_artifact_refs,
                tuple(produced_artifact_refs or ()),
            )
            retained_warnings = _append_unique_issues(
                job.warnings,
                tuple(warnings or ()),
            )
            retained_blockers = _append_unique_issues(
                job.blockers,
                tuple(blockers or ()),
            )
            if status in {
                ResearchJobStatus.PARTIAL,
                ResearchJobStatus.FAILED,
                ResearchJobStatus.AMBIGUOUS,
                ResearchJobStatus.RECONCILIATION_REQUIRED,
            } and not retained_blockers:
                raise ValueError(f"{status.value} reconciliation requires blockers")
            if status is ResearchJobStatus.AMBIGUOUS and retryable:
                raise ValueError("ambiguous reconciliation cannot be retryable")
            reconciled = replace(
                job,
                status=status,
                lease_id=None if _is_terminal(status) else job.lease_id,
                lease_expires_at=None if _is_terminal(status) else job.lease_expires_at,
                produced_artifact_refs=retained_refs,
                warnings=retained_warnings,
                blockers=retained_blockers,
                retryable=retryable,
            )
            saved = self._store.save(reconciled, expected_status=job.status)
        except (RuntimeError, ValueError, TypeError) as exc:
            return _error(command, "research_job_reconciliation_failed", str(exc))
        return _success(command, saved)


def submit_research_job(
    job: ResearchJob,
    *,
    job_store: ResearchJobStore,
) -> ApplicationResult:
    """Convenience wrapper for :meth:`ResearchJobLifecycleService.submit`."""
    return ResearchJobLifecycleService(job_store).submit(job)


def get_research_job(job_id: str, *, job_store: ResearchJobStore) -> ApplicationResult:
    """Convenience wrapper for the bounded status command."""
    return ResearchJobLifecycleService(job_store).status(job_id)


def cancel_research_job(
    job_id: str,
    *,
    actor: str,
    reason: str,
    job_store: ResearchJobStore,
) -> ApplicationResult:
    """Convenience wrapper for the bounded cancellation command."""
    return ResearchJobLifecycleService(job_store).cancel(
        job_id,
        actor=actor,
        reason=reason,
    )


def reconcile_research_job(
    job_id: str,
    *,
    actor: str,
    status: ResearchJobStatus,
    job_store: ResearchJobStore,
    produced_artifact_refs: Sequence[ArtifactReportRef] | None = None,
    warnings: Sequence[ResearchIssue] | None = None,
    blockers: Sequence[ResearchIssue] | None = None,
    retryable: bool = False,
) -> ApplicationResult:
    """Convenience wrapper for the bounded reconciliation command."""
    return ResearchJobLifecycleService(job_store).reconcile(
        job_id,
        actor=actor,
        status=status,
        produced_artifact_refs=produced_artifact_refs,
        warnings=warnings,
        blockers=blockers,
        retryable=retryable,
    )


def _authorize(job: ResearchJob, actor: str) -> None:
    """Require the submitting actor or requester for this bounded command."""
    if actor not in {job.actor, job.requested_by}:
        raise ValueError(f"actor {actor!r} is not authorized for job {job.job_id}")


def _assert_same_cancellation(job: ResearchJob, actor: str, reason: str) -> None:
    """Make repeated cancellation idempotent while rejecting drift."""
    for issue in job.blockers:
        if issue.code != "operator_cancelled":
            continue
        if str(issue.details.get("actor") or "") != actor:
            raise ValueError("cancel actor conflicts with the accepted cancellation")
        if issue.message != reason:
            raise ValueError("cancel reason conflicts with the accepted cancellation")
        return
    raise ValueError("cancelled job has no matching cancellation receipt")


def _append_unique_refs(
    existing: Sequence[ArtifactReportRef], additions: Sequence[ArtifactReportRef]
) -> tuple[ArtifactReportRef, ...]:
    """Append artifact refs by URI without changing previously retained order."""
    values = list(existing)
    known = {item.uri for item in existing}
    for item in additions:
        if not isinstance(item, ArtifactReportRef):
            raise TypeError("produced_artifact_refs must contain ArtifactReportRef values")
        if item.uri not in known:
            values.append(item)
            known.add(item.uri)
    return tuple(values)


def _append_unique_issues(
    existing: Sequence[ResearchIssue], additions: Sequence[ResearchIssue]
) -> tuple[ResearchIssue, ...]:
    """Append structured issues by code/message/details identity."""
    values = list(existing)
    known = {(item.code, item.message, repr(sorted(item.details.items()))) for item in existing}
    for item in additions:
        if not isinstance(item, ResearchIssue):
            raise TypeError("issues must contain ResearchIssue values")
        key = (item.code, item.message, repr(sorted(item.details.items())))
        if key not in known:
            values.append(item)
            known.add(key)
    return tuple(values)


def _required_text(value: object, label: str) -> str:
    """Normalize required command text at the application boundary."""
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"{label} is required")
    return text


def _is_terminal(status: ResearchJobStatus) -> bool:
    """Return whether a requested status closes the persisted job."""
    return status in {
        ResearchJobStatus.SUCCEEDED,
        ResearchJobStatus.FAILED,
        ResearchJobStatus.CANCELLED,
        ResearchJobStatus.AMBIGUOUS,
        ResearchJobStatus.RECONCILIATION_REQUIRED,
    }


def _success(command: str, job: ResearchJob) -> ApplicationResult:
    """Return one bounded job projection."""
    return success_result(command=command, data={"research_job": job.to_dict()})


def _error(command: str, code: str, message: str) -> ApplicationResult:
    """Return one structured command failure."""
    return error_result(command=command, code=code, message=message)


__all__ = [
    "RESEARCH_CANCEL_JOB",
    "RESEARCH_GET_JOB",
    "RESEARCH_RECONCILE_JOB",
    "RESEARCH_SUBMIT_JOB",
    "ResearchJobLifecycleService",
    "ResearchJobStore",
    "cancel_research_job",
    "get_research_job",
    "reconcile_research_job",
    "submit_research_job",
]
