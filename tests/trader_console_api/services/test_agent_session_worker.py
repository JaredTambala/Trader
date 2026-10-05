"""Agent-session command worker contracts.

Subject: Durable claim, runtime application, public-state retention, and lost-response handling.
Level: In-process worker orchestration with typed runtime/repository doubles.
Collaborators: Agent command boundary and Console worker repository protocol; no SQL or MCP.
Guarantees: Human commands reach the runtime, state is retained after application, and unknown outcomes are
marked ambiguous instead of replayed.
Non-goals: LangGraph provider behavior, database isolation, and browser layout.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any, Literal, cast

from trader_console_api.agent_session_worker import AgentSessionCommandWorker
from trader_console_api.contracts import AgentSessionCommandRecord
from trader_console_api.repositories.agent_session_worker import AgentSessionWorkerRepository


def _command(command: Literal["inspect", "interrupt", "resume", "cancel"] = "interrupt") -> AgentSessionCommandRecord:
    """Build one leased worker command."""
    return AgentSessionCommandRecord(
        command_id="00000000-0000-0000-0000-000000000001",
        session_id="session-1",
        command=command,
        idempotency_key="intent-1",
        requested_by="human:jared",
        status="accepted",
        reason="Review evidence.",
        requested_at=datetime.now(timezone.utc),
        worker_id="worker-1",
        attempt=1,
    )


class _Runtime:
    """Runtime double exposing the agent-owned lifecycle boundary."""

    def __init__(self, *, fail: bool = False) -> None:
        self.calls: list[str] = []
        self.fail = fail

    async def inspect(self, _session: Any) -> dict[str, Any]:
        """Return bounded state after each command."""
        self.calls.append("inspect")
        return {"status": "awaiting_operator", "next_sequence": 2}

    async def interrupt(self, _session: Any, _request: Any) -> None:
        """Record an interrupt request or simulate an unknown runtime response."""
        self.calls.append("interrupt")
        if self.fail:
            raise RuntimeError("runtime response was lost")

    async def resume(self, _session: Any, _request: Any) -> None:
        """Satisfy the runtime protocol for command-boundary coverage."""
        self.calls.append("resume")

    async def cancel(self, _session: Any, _request: Any) -> None:
        """Satisfy the runtime protocol for command-boundary coverage."""
        self.calls.append("cancel")


class _Session:
    """Repository transaction double with one command and captured outcomes."""

    def __init__(self, command: AgentSessionCommandRecord, runtime_session: Any) -> None:
        self.command = command
        self.runtime_session = runtime_session
        self.finished: list[tuple[str, str, str]] = []
        self.public_state: dict[str, Any] | None = None
        self.heartbeat_calls = 0

    async def claim_next(self, **_kwargs: Any) -> AgentSessionCommandRecord | None:
        """Return the command once, then model an empty queue."""
        command, self.command = self.command, None  # type: ignore[assignment]
        return command

    async def load_session(self, _session_id: str) -> Any:
        """Return the immutable owner-bound session fixture."""
        return self.runtime_session

    async def upsert_public_state(self, _session: Any, state: dict[str, Any], *, checkpoint_sequence: int | None) -> None:
        """Capture the redacted runtime state and checkpoint identity."""
        self.public_state = {**state, "checkpoint_sequence": checkpoint_sequence}

    async def heartbeat(self, _command_id: Any, *, worker_id: str, lease_seconds: int) -> bool:
        """Renew the worker lease while a command is active."""
        assert worker_id == "worker-1"
        assert lease_seconds == 1
        self.heartbeat_calls += 1
        return True

    async def finish(self, _command_id: Any, *, worker_id: str, status: str, outcome_code: str | None, outcome_message: str | None) -> bool:
        """Capture the worker's terminal command receipt."""
        self.finished.append((status, outcome_code or "", worker_id))
        return True


class _Repository:
    """Repository double yielding one shared worker transaction fixture."""

    def __init__(self, session: _Session) -> None:
        self.session_fixture = session

    @asynccontextmanager
    async def session(self):
        """Yield the transaction double."""
        yield self.session_fixture


def test_worker_applies_interrupt_and_retains_public_state() -> None:
    """A claimed human command reaches the runtime and stores its fresh projection."""
    session = _Session(
        _command(),
        SimpleNamespace(session_id="session-1", operator_id="human:jared", session_digest="a" * 64),
    )
    runtime = _Runtime()

    @asynccontextmanager
    async def runtime_factory():
        yield runtime

    worker = AgentSessionCommandWorker(
        cast(AgentSessionWorkerRepository, _Repository(session)),
        runtime_factory,
        worker_id="worker-1",
    )
    import asyncio

    assert asyncio.run(worker.run_once()) is True
    assert runtime.calls == ["interrupt", "inspect"]
    assert session.public_state == {"status": "awaiting_operator", "next_sequence": 2, "checkpoint_sequence": 1}
    assert session.finished == [("completed", "runtime_applied", "worker-1")]


def test_worker_marks_lost_runtime_response_ambiguous() -> None:
    """A provider/runtime failure never causes a worker replay."""
    session = _Session(
        _command(),
        SimpleNamespace(session_id="session-1", operator_id="human:jared", session_digest="a" * 64),
    )
    runtime = _Runtime(fail=True)

    @asynccontextmanager
    async def runtime_factory():
        yield runtime

    worker = AgentSessionCommandWorker(
        cast(AgentSessionWorkerRepository, _Repository(session)),
        runtime_factory,
        worker_id="worker-1",
    )
    import asyncio

    assert asyncio.run(worker.run_once()) is True
    assert session.finished == [("ambiguous", "runtime_outcome_unknown", "worker-1")]
    assert session.public_state is None


def test_worker_rejects_non_owner_before_runtime() -> None:
    """A mismatched human identity fails closed without invoking the runtime."""
    session = _Session(
        _command(),
        SimpleNamespace(session_id="session-1", operator_id="human:other", session_digest="a" * 64),
    )
    runtime = _Runtime()

    @asynccontextmanager
    async def runtime_factory():
        yield runtime

    worker = AgentSessionCommandWorker(
        cast(AgentSessionWorkerRepository, _Repository(session)),
        runtime_factory,
        worker_id="worker-1",
    )
    import asyncio

    assert asyncio.run(worker.run_once()) is True
    assert runtime.calls == []
    assert session.finished == [("rejected", "session_owner_mismatch", "worker-1")]


def test_worker_renews_a_long_running_runtime_lease() -> None:
    """A command longer than its lease remains owned through heartbeat renewal."""
    import asyncio

    class _SlowRuntime(_Runtime):
        async def interrupt(self, _session: Any, _request: Any) -> None:
            await asyncio.sleep(1.1)
            await super().interrupt(_session, _request)

    session = _Session(
        _command(),
        SimpleNamespace(session_id="session-1", operator_id="human:jared", session_digest="a" * 64),
    )
    runtime = _SlowRuntime()

    @asynccontextmanager
    async def runtime_factory():
        yield runtime

    worker = AgentSessionCommandWorker(
        cast(AgentSessionWorkerRepository, _Repository(session)),
        runtime_factory,
        worker_id="worker-1",
        lease_seconds=1,
    )
    assert asyncio.run(worker.run_once()) is True
    assert session.heartbeat_calls >= 1
    assert session.finished == [("completed", "runtime_applied", "worker-1")]
