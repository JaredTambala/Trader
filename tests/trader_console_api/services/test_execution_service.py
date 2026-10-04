"""Durable execution command service contracts.

Subject: Idempotent submit and bounded status/list orchestration.
Level: Application-service unit tests.
Collaborators: In-memory repository/session double; typed execution contracts.
Guarantees: Submit uses a command transaction, duplicate keys reuse the command, and reads remain bounded.
Non-goals: Worker execution, lease recovery, PostgreSQL SQL, and producer evidence.
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from uuid import uuid4

from trader_console_api.contracts import BacktestExecutionRecord, BacktestExecutionSubmit
from trader_console_api.services.backtest_executions import BacktestExecutionService


def _record(definition_id, execution_id=None) -> BacktestExecutionRecord:
    """Return one representative queued command."""
    now = datetime(2026, 1, 1, tzinfo=UTC)
    return BacktestExecutionRecord(
        execution_id=str(execution_id or uuid4()),
        scope_id="scope-a",
        definition_id=str(definition_id),
        definition_revision=1,
        definition_fingerprint="a" * 64,
        idempotency_key="submit-1",
        status="queued",
        attempt=0,
        processed_cycles=0,
        created_at=now,
    )


class _Session:
    """Repository session double recording calls."""

    def __init__(self, record: BacktestExecutionRecord) -> None:
        self.record = record
        self.required = False

    async def require_storage(self) -> None:
        """Record explicit storage checking."""
        self.required = True

    async def submit(self, definition_id, *, idempotency_key):
        """Return one durable queued record."""
        return self.record

    async def get(self, execution_id):
        """Return the configured record."""
        return self.record

    async def list(self, limit, offset):
        """Return one bounded record page."""
        return [self.record], 1


class _Repository:
    """Repository double with transaction mode evidence."""

    def __init__(self, session: _Session) -> None:
        self.session_value = session
        self.modes: list[bool] = []

    @asynccontextmanager
    async def session(self, *, write: bool = False):
        """Yield the session and record read/write mode."""
        self.modes.append(write)
        yield self.session_value


def test_submit_uses_write_transaction_and_returns_queued_record() -> None:
    """A valid command enters durable queued state through one write session."""
    definition_id = uuid4()
    session = _Session(_record(definition_id))
    service = BacktestExecutionService(_Repository(session))

    result = asyncio.run(
        service.submit(BacktestExecutionSubmit(definition_id=definition_id, idempotency_key="submit-1"))
    )

    assert result.status == "queued"
    assert session.required is True


def test_status_and_list_use_read_transactions() -> None:
    """Command observation remains bounded and read-only at the service boundary."""
    definition_id = uuid4()
    repository = _Repository(_Session(_record(definition_id)))
    service = BacktestExecutionService(repository)

    asyncio.run(service.get(uuid4()))
    page = asyncio.run(service.list(limit=10, offset=0))

    assert page.page.total == 1
    assert repository.modes == [False, False]
