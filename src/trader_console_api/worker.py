"""Restart-safe execution worker seam for Console backtest commands.

The worker owns leases and durable command transitions. A deployment composes a
real executor that resolves the frozen definition through the maintained
catalogue and invokes the canonical ``BacktestRunner``; this module never
pretends that an absent executor produced evidence.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, replace
from datetime import datetime
import hashlib
from typing import Literal, Protocol
from uuid import UUID

from trader_research.governance import (
    ArtifactReportRef,
    ResearchIssue,
    ResearchJob,
    ResearchJobStatus,
)

from .contracts import BacktestDefinition
from .repositories.backtest_executions import BacktestExecutionRepository


ProgressSink = Callable[[int, int | None, datetime | None], Awaitable[None]]
TerminalStatus = Literal["completed", "partial", "failed", "reconciliation_required"]


@dataclass(frozen=True)
class ExecutionOutcome:
    """Executor result mapped to one durable terminal command state."""

    status: TerminalStatus
    processed_cycles: int
    total_cycles: int | None
    warnings: tuple[str, ...] = ()
    error_code: str | None = None
    error_message: str | None = None


class BacktestExecutor(Protocol):
    """Injected canonical runner adapter owned by worker composition."""

    async def execute(
        self,
        definition: BacktestDefinition,
        *,
        run_id: str,
        progress: ProgressSink,
    ) -> ExecutionOutcome:
        """Execute one frozen definition through the internal backtest broker."""
        ...


class AmbiguousExecutionError(RuntimeError):
    """The worker cannot prove whether producer execution reached a terminal state."""


ResearchJobProgressSink = Callable[[datetime | None], Awaitable[None]]
ResearchJobOutcomeStatus = Literal[
    "succeeded", "partial", "failed", "ambiguous", "reconciliation_required"
]


@dataclass(frozen=True)
class ResearchJobExecutionOutcome:
    """Bounded producer outcome returned by a ResearchJob executor adapter."""

    status: ResearchJobOutcomeStatus
    produced_artifact_refs: tuple[ArtifactReportRef, ...] = ()
    warnings: tuple[ResearchIssue, ...] = ()
    blockers: tuple[ResearchIssue, ...] = ()
    retryable: bool = False


class ResearchJobExecutor(Protocol):
    """Injected adapter that resolves a job into the canonical BacktestRunner."""

    async def execute(
        self,
        job: ResearchJob,
        *,
        run_id: str,
        progress: ResearchJobProgressSink,
    ) -> ResearchJobExecutionOutcome:
        """Execute one admitted job under its deterministic producer run ID."""
        ...


class LeaseCapableResearchJobStore(Protocol):
    """Persistence contract required by the research worker."""

    def claim_next(
        self,
        *,
        worker_id: str,
        lease_seconds: int,
        max_attempts: int,
    ) -> ResearchJob | None:
        """Claim one queued job or return no work."""
        ...

    def heartbeat(
        self,
        job_id: str,
        *,
        worker_id: str,
        lease_id: str,
        lease_seconds: int,
    ) -> bool:
        """Renew one active lease."""
        ...

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
        """Persist one outcome when the worker still owns the lease."""
        ...


class ResearchJobWorker:
    """Claim approved research jobs and retain restart-safe producer outcomes."""

    def __init__(
        self,
        store: LeaseCapableResearchJobStore,
        executor: ResearchJobExecutor,
        *,
        worker_id: str,
        lease_seconds: int = 60,
        max_attempts: int = 3,
    ) -> None:
        """Bind a worker identity, durable job store, and canonical executor."""
        if not worker_id.strip():
            raise ValueError("worker_id must not be blank")
        if lease_seconds < 1:
            raise ValueError("lease_seconds must be positive")
        if max_attempts < 1:
            raise ValueError("max_attempts must be positive")
        self._store = store
        self._executor = executor
        self._worker_id = worker_id
        self._lease_seconds = lease_seconds
        self._max_attempts = max_attempts

    async def run_once(self) -> bool:
        """Claim and process one approved job, returning whether work was claimed."""
        job = self._store.claim_next(
            worker_id=self._worker_id,
            lease_seconds=self._lease_seconds,
            max_attempts=self._max_attempts,
        )
        if job is None:
            return False
        run_id = deterministic_research_run_id(job.job_id, job.request_digest)
        if job.operation_kind.value != "backtest":
            self._finish_failed(
                job,
                ResearchIssue(
                    code="unsupported_research_operation",
                    message="This worker only executes admitted backtest jobs.",
                    details={"operation_kind": job.operation_kind.value},
                ),
            )
            return True

        async def progress(last_decision_at: datetime | None = None) -> None:
            """Renew the lease while the canonical producer is running."""
            renewed = self._store.heartbeat(
                job.job_id,
                worker_id=self._worker_id,
                lease_id=job.lease_id or "",
                lease_seconds=self._lease_seconds,
            )
            if not renewed:
                raise AmbiguousExecutionError(
                    "The worker lost its ResearchJob lease during BacktestRunner execution"
                )

        try:
            outcome = await self._executor.execute(
                job,
                run_id=run_id,
                progress=progress,
            )
        except AmbiguousExecutionError as exc:
            outcome = ResearchJobExecutionOutcome(
                status="reconciliation_required",
                blockers=(
                    ResearchIssue(
                        code="ambiguous_producer_outcome",
                        message=str(exc),
                        details={"job_id": job.job_id},
                    ),
                ),
            )
        except Exception as exc:  # pragma: no cover - adapter failures vary
            outcome = ResearchJobExecutionOutcome(
                status="failed",
                blockers=(
                    ResearchIssue(
                        code="worker_execution_failed",
                        message=str(exc),
                        details={"job_id": job.job_id},
                    ),
                ),
            )

        if (
            outcome.status
            in {"partial", "failed", "ambiguous", "reconciliation_required"}
            and not outcome.blockers
        ):
            outcome = replace(
                outcome,
                blockers=(
                    ResearchIssue(
                        code="missing_outcome_blocker",
                        message="Non-success research outcomes require a blocker.",
                        details={"job_id": job.job_id},
                    ),
                ),
            )
        finished = self._store.finish(
            job.job_id,
            worker_id=self._worker_id,
            lease_id=job.lease_id or "",
            status=ResearchJobStatus(outcome.status),
            produced_artifact_refs=outcome.produced_artifact_refs,
            warnings=outcome.warnings,
            blockers=outcome.blockers,
            retryable=outcome.retryable,
        )
        if finished is None:
            raise AmbiguousExecutionError(
                "The worker could not retain the ResearchJob terminal receipt"
            )
        return True

    def _finish_failed(self, job: ResearchJob, blocker: ResearchIssue) -> None:
        """Persist a bounded failure before invoking an unsupported producer."""
        finished = self._store.finish(
            job.job_id,
            worker_id=self._worker_id,
            lease_id=job.lease_id or "",
            status=ResearchJobStatus.FAILED,
            blockers=(blocker,),
        )
        if finished is None:
            raise AmbiguousExecutionError(
                "The worker could not retain the unsupported-operation receipt"
            )


def deterministic_execution_run_id(execution_id: str, fingerprint: str) -> str:
    """Derive one stable producer run identity from command identity and content."""
    return hashlib.sha256(
        f"console-backtest:{execution_id}:{fingerprint}".encode()
    ).hexdigest()


def deterministic_research_run_id(job_id: str, request_digest: str) -> str:
    """Derive one stable producer run ID from an admitted research request."""
    return hashlib.sha256(
        f"research-backtest:{job_id}:{request_digest}".encode()
    ).hexdigest()


class BacktestExecutionWorker:
    """Claim one command, execute through an injected adapter, and persist outcome."""

    def __init__(
        self,
        repository: BacktestExecutionRepository,
        executor: BacktestExecutor,
        *,
        worker_id: str,
        lease_seconds: int = 60,
        max_attempts: int = 3,
    ) -> None:
        """Bind a worker identity, bounded lease, repository and executor."""
        if not worker_id.strip():
            raise ValueError("worker_id must not be blank")
        if lease_seconds < 1:
            raise ValueError("lease_seconds must be positive")
        if max_attempts < 1:
            raise ValueError("max_attempts must be positive")
        self._repository = repository
        self._executor = executor
        self._worker_id = worker_id
        self._lease_seconds = lease_seconds
        self._max_attempts = max_attempts

    async def run_once(self) -> bool:
        """Claim and process one command, returning whether work was claimed."""
        async with self._repository.session(write=True) as session:
            command = await session.claim_next(
                worker_id=self._worker_id,
                lease_seconds=self._lease_seconds,
                max_attempts=self._max_attempts,
            )
            if command is None:
                return False
            definition = await session.load_definition(
                UUID(command.definition_id), command.definition_revision
            )
            if definition is None:
                await session.finish(
                    UUID(command.execution_id),
                    worker_id=self._worker_id,
                    status="failed",
                    run_id=None,
                    processed_cycles=0,
                    total_cycles=None,
                    warning_summary=[],
                    error_code="definition_revision_missing",
                    error_message="The immutable definition revision is unavailable",
                )
                return True
            run_id = deterministic_execution_run_id(
                command.execution_id, command.definition_fingerprint
            )
            if not await session.reserve_run_id(
                UUID(command.execution_id), worker_id=self._worker_id, run_id=run_id
            ):
                return True

        async def progress(
            processed_cycles: int,
            total_cycles: int | None,
            last_decision_at: datetime | None,
        ) -> None:
            """Persist coarse progress while the worker lease remains valid."""
            async with self._repository.session(write=True) as progress_session:
                renewed = await progress_session.heartbeat(
                    UUID(command.execution_id),
                    worker_id=self._worker_id,
                    processed_cycles=processed_cycles,
                    total_cycles=total_cycles,
                    last_decision_at=last_decision_at,
                    lease_seconds=self._lease_seconds,
                )
                if not renewed:
                    raise AmbiguousExecutionError(
                        "The worker lost its lease while producer execution was active"
                    )

        try:
            outcome = await self._executor.execute(
                definition,
                run_id=run_id,
                progress=progress,
            )
        except AmbiguousExecutionError as exc:
            outcome = ExecutionOutcome(
                status="reconciliation_required",
                processed_cycles=0,
                total_cycles=None,
                error_code="ambiguous_producer_outcome",
                error_message=str(exc),
            )
        except Exception as exc:  # pragma: no cover - adapter failures vary
            outcome = ExecutionOutcome(
                status="failed",
                processed_cycles=0,
                total_cycles=None,
                error_code="worker_execution_failed",
                error_message=str(exc),
            )

        async with self._repository.session(write=True) as session:
            finished = await session.finish(
                UUID(command.execution_id),
                worker_id=self._worker_id,
                status=outcome.status,
                run_id=run_id,
                processed_cycles=outcome.processed_cycles,
                total_cycles=outcome.total_cycles,
                warning_summary=list(outcome.warnings),
                error_code=outcome.error_code,
                error_message=outcome.error_message,
            )
            if not finished:
                raise AmbiguousExecutionError(
                    "The worker could not retain its terminal execution receipt"
                )
        return True


__all__ = [
    "AmbiguousExecutionError",
    "BacktestExecutionWorker",
    "BacktestExecutor",
    "ExecutionOutcome",
    "ProgressSink",
    "ResearchJobExecutionOutcome",
    "ResearchJobExecutor",
    "ResearchJobProgressSink",
    "ResearchJobWorker",
    "LeaseCapableResearchJobStore",
    "deterministic_execution_run_id",
    "deterministic_research_run_id",
]
