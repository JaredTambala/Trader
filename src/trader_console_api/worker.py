"""Restart-safe execution worker seam for Console backtest commands.

The worker owns leases and durable command transitions. A deployment composes a
real executor that resolves the frozen definition through the maintained
catalogue and invokes the canonical ``BacktestRunner``; this module never
pretends that an absent executor produced evidence.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime
import hashlib
from typing import Literal, Protocol
from uuid import UUID

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


def deterministic_execution_run_id(execution_id: str, fingerprint: str) -> str:
    """Derive one stable producer run identity from command identity and content."""
    return hashlib.sha256(f"console-backtest:{execution_id}:{fingerprint}".encode()).hexdigest()


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
                await progress_session.heartbeat(
                    UUID(command.execution_id),
                    worker_id=self._worker_id,
                    processed_cycles=processed_cycles,
                    total_cycles=total_cycles,
                    last_decision_at=last_decision_at,
                    lease_seconds=self._lease_seconds,
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
            await session.finish(
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
        return True


__all__ = [
    "AmbiguousExecutionError",
    "BacktestExecutionWorker",
    "BacktestExecutor",
    "ExecutionOutcome",
    "ProgressSink",
    "deterministic_execution_run_id",
]
