"""Restart-safe worker lifecycle contracts for durable Console commands.

Subject: Lease claim, deterministic run identity, heartbeat progress, and terminal outcomes.
Level: Worker unit tests.
Collaborators: In-memory repository/session double and injected executor.
Guarantees: The worker never invents success, persists progress through the lease, and marks ambiguous adapters for reconciliation.
Non-goals: PostgreSQL locking, concrete BacktestRunner composition, and producer event persistence.
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

from trader_console_api.contracts import BacktestDefinition, BacktestExecutionRecord
from trader_console_api.data_scope_contracts import BacktestDataScopeHandoff, DataScopeEvidenceStatus, DataScopeSourcePolicy
from trader_console_api.worker import (
    AmbiguousExecutionError,
    BacktestExecutionWorker,
    ExecutionOutcome,
    deterministic_execution_run_id,
)
from tests.trader_console_api.support import implementation_lineage


def _definition() -> BacktestDefinition:
    """Build one frozen definition for worker adapter calls."""
    return BacktestDefinition(
        display_name="Smoke",
        strategy_profile_id="noop",
        strategy_catalogue_version="standard-1",
        strategy_implementation_lineage=implementation_lineage(),
        risk_profile_id="noop",
        risk_catalogue_version="standard-1",
        risk_implementation_lineage=implementation_lineage(kind="risk", suffix="risk"),
        asset_class="stock",
        symbols=("AAPL",),
        timeframe="1Min",
        start=datetime(2026, 1, 1, tzinfo=UTC),
        end=datetime(2026, 1, 1, 1, tzinfo=UTC),
        initial_cash=100_000,
        data_scope=BacktestDataScopeHandoff(
            saved_scope_id="00000000-0000-0000-0000-000000000001", fingerprint="a" * 64,
            asset_class="stock", symbols=("AAPL",), timeframe="1Min", interval="1Min",
            start=datetime(2026, 1, 1, tzinfo=UTC), end=datetime(2026, 1, 1, 1, tzinfo=UTC),
            source_policy=DataScopeSourcePolicy(provider="fixture", source="fixture"),
            manifest_artifact_id="manifest-1", quality_artifact_id="quality-1",
            evidence_status=DataScopeEvidenceStatus.ACTIVE,
        ),
    )


def _command() -> BacktestExecutionRecord:
    """Build one claimed command record."""
    now = datetime(2026, 1, 1, tzinfo=UTC)
    return BacktestExecutionRecord(
        execution_id=str(uuid4()),
        scope_id="scope-a",
        definition_id=str(uuid4()),
        definition_revision=1,
        definition_fingerprint="a" * 64,
        idempotency_key="submit-1",
        status="running",
        attempt=1,
        worker_id="worker-a",
        processed_cycles=0,
        created_at=now,
        started_at=now,
        heartbeat_at=now,
    )


class _Session:
    """Repository session double recording worker transitions."""

    def __init__(
        self, command: BacktestExecutionRecord, *,
        heartbeat_ok: bool = True, finish_ok: bool = True,
    ) -> None:
        self.command = command
        self.calls: list[str] = []
        self.heartbeat_ok = heartbeat_ok
        self.finish_ok = finish_ok

    async def claim_next(self, *, worker_id, lease_seconds, max_attempts):
        """Return one claimed command once."""
        self.calls.append("claim")
        return self.command if self.calls.count("claim") == 1 else None

    async def load_definition(self, definition_id: UUID, revision: int):
        """Return the immutable definition selected by the command."""
        self.calls.append("load")
        return _definition()

    async def reserve_run_id(self, execution_id, *, worker_id, run_id):
        """Record deterministic run reservation."""
        self.calls.append(f"reserve:{run_id}")
        return True

    async def heartbeat(self, execution_id, **kwargs):
        """Record coarse progress heartbeat."""
        self.calls.append("heartbeat")
        return self.heartbeat_ok

    async def finish(self, execution_id, **kwargs):
        """Record terminal state update."""
        self.calls.append(f"finish:{kwargs['status']}")
        return self.finish_ok


class _Repository:
    """Repository double yielding one session per worker transaction."""

    def __init__(self, session: _Session) -> None:
        self.session_value = session

    @asynccontextmanager
    async def session(self, *, write: bool = False):
        """Yield the same session while preserving transaction boundaries."""
        yield self.session_value


class _Executor:
    """Injected executor that emits one progress update and succeeds."""

    async def execute(self, definition, *, run_id, progress):
        """Emit progress and return a completed outcome."""
        await progress(4, 10, datetime(2026, 1, 1, tzinfo=UTC))
        return ExecutionOutcome(status="completed", processed_cycles=10, total_cycles=10)


class _AmbiguousExecutor:
    """Injected executor that cannot prove producer outcome."""

    async def execute(self, definition, *, run_id, progress):
        """Raise the explicit ambiguity signal."""
        raise AmbiguousExecutionError("producer connection dropped")


class _OutcomeExecutor:
    """Injected executor returning an explicit producer outcome."""

    def __init__(self, outcome: ExecutionOutcome) -> None:
        self.outcome = outcome

    async def execute(self, definition, *, run_id, progress):
        """Return the configured terminal result without synthesizing success."""
        del definition, run_id, progress
        return self.outcome


class _UnavailableRepository:
    """Command store that cannot establish a write transaction."""

    @asynccontextmanager
    async def session(self, *, write: bool = False):
        """Fail before command claim or producer execution."""
        del write
        raise OSError("command store unavailable")
        yield  # pragma: no cover


class _NeverExecutor:
    """Executor that detects an unsafe call after command-store failure."""

    async def execute(self, definition, *, run_id, progress):
        """Refuse execution without a durable command claim."""
        raise AssertionError("producer must not run without a command store")


def test_worker_claims_reserves_heartbeats_and_finishes_with_deterministic_run_id() -> None:
    """A successful adapter path records lease progress and one terminal completion."""
    command = _command()
    session = _Session(command)
    worker = BacktestExecutionWorker(
        _Repository(session), _Executor(), worker_id="worker-a", lease_seconds=30
    )

    assert asyncio.run(worker.run_once()) is True
    expected = deterministic_execution_run_id(command.execution_id, command.definition_fingerprint)
    assert f"reserve:{expected}" in session.calls
    assert "heartbeat" in session.calls
    assert "finish:completed" in session.calls


def test_worker_marks_ambiguous_adapter_outcome_for_reconciliation() -> None:
    """An uncertain producer result is never converted into a retryable failure."""
    session = _Session(_command())
    worker = BacktestExecutionWorker(
        _Repository(session), _AmbiguousExecutor(), worker_id="worker-a"
    )

    asyncio.run(worker.run_once())

    assert "finish:reconciliation_required" in session.calls


@pytest.mark.parametrize("status", ["partial", "failed"])
def test_worker_preserves_non_success_producer_outcomes(status: str) -> None:
    """A partial or failed producer result remains visible as its own terminal state."""
    session = _Session(_command())
    worker = BacktestExecutionWorker(
        _Repository(session),
        _OutcomeExecutor(
            ExecutionOutcome(
                status=status, processed_cycles=2, total_cycles=10,
                warnings=("bounded replay stopped",), error_code="producer_failure",
            )
        ),
        worker_id="worker-a",
    )

    assert asyncio.run(worker.run_once()) is True
    assert f"finish:{status}" in session.calls


def test_worker_does_not_report_success_after_losing_progress_lease() -> None:
    """A lost lease during producer progress requires reconciliation, never completion."""
    session = _Session(_command(), heartbeat_ok=False)
    worker = BacktestExecutionWorker(
        _Repository(session), _Executor(), worker_id="worker-a"
    )

    asyncio.run(worker.run_once())

    assert "finish:completed" not in session.calls
    assert "finish:reconciliation_required" in session.calls


def test_worker_fails_if_terminal_receipt_cannot_be_persisted() -> None:
    """A lost lease at finish cannot be reported as a successful worker command."""
    session = _Session(_command(), finish_ok=False)
    worker = BacktestExecutionWorker(
        _Repository(session), _Executor(), worker_id="worker-a"
    )

    with pytest.raises(AmbiguousExecutionError, match="terminal execution receipt"):
        asyncio.run(worker.run_once())


def test_worker_does_not_run_producer_during_command_store_outage() -> None:
    """An unavailable command store prevents a claim and leaves execution untouched."""
    worker = BacktestExecutionWorker(
        _UnavailableRepository(), _NeverExecutor(), worker_id="worker-a"
    )

    with pytest.raises(OSError, match="command store unavailable"):
        asyncio.run(worker.run_once())
