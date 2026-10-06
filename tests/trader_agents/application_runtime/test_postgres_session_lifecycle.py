"""Postgres-backed process recovery qualification for governed sessions.

Subject: Exact terminal checkpoint recovery after a lost command response.
Level: PostgreSQL adapter integration with a fresh operating-system process.
Collaborators: Real LangGraph Postgres savers and runtime graphs with static
model/MCP doubles; no canonical research Postgres or Console worker.
Guarantees: A new process inspects the same bounded terminal state and retrying
start/cancel cannot re-execute a decision or emit a second terminal event.
Non-goals: Cross-process writer races, live providers, and model qualification.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from uuid import uuid4

import anyio
import pytest

from tests.trader_agents.application_runtime.test_interrupt import _runtime
from tests.trader_agents.application_runtime.test_session_lifecycle_qualification import (
    _cancellation,
)
from trader_agents import (
    AgentEventEmitter,
    AgentEventName,
    RecordingObservabilityEventSink,
    open_postgres_checkpointer,
)


@pytest.mark.postgres
def test_fresh_process_inspects_lost_terminal_response_without_reexecution() -> None:
    """A separate Python process reads and replays one exact Postgres checkpoint."""
    dsn = os.environ.get("TRADER_AGENTS_CHECKPOINT_DSN")
    if not dsn:
        pytest.skip("TRADER_AGENTS_CHECKPOINT_DSN is required")
    session_id = f"session-lifecycle-process-{uuid4().hex}"
    first_sink = RecordingObservabilityEventSink()

    async def _commit_before_lost_response() -> tuple[str, str]:
        async with open_postgres_checkpointer(dsn=dsn, setup=True) as saver:
            runtime, session = _runtime(session_id)
            runtime.checkpointer = saver
            runtime.event_emitter = AgentEventEmitter(
                sink=first_sink, process_instance_id="first-process"
            )
            await runtime.start(session)
            await runtime.cancel(session, _cancellation(session.operator_id))
            state = await runtime.inspect(session)
            return state["branch_id"], state["decision_receipt_ref"]["uri"]

    branch_id, receipt_uri = anyio.run(_commit_before_lost_response)
    script = """
import anyio
import json
import os
from tests.trader_agents.application_runtime.test_interrupt import _runtime
from tests.trader_agents.application_runtime.test_session_lifecycle_qualification import _cancellation
from trader_agents import AgentEventEmitter, AgentEventName, RecordingObservabilityEventSink, open_postgres_checkpointer

async def recover():
    async with open_postgres_checkpointer(dsn=os.environ["TRADER_AGENTS_CHECKPOINT_DSN"]) as saver:
        runtime, session = _runtime(os.environ["TRD313_SESSION_ID"])
        runtime.checkpointer = saver
        sink = RecordingObservabilityEventSink()
        runtime.event_emitter = AgentEventEmitter(sink=sink, process_instance_id="fresh-process")
        state = await runtime.inspect(session)
        replay = await runtime.start(session)
        retry = await runtime.cancel(session, _cancellation(session.operator_id))
        return {
            "status": state["status"],
            "branch_id": state["branch_id"],
            "receipt_uri": state["decision_receipt_ref"]["uri"],
            "replay_status": replay.status,
            "retry_status": retry.status,
            "model_calls": len(runtime.coordinator.model_runner.client.requests),
            "decision_writes": len(runtime.coordinator.mcp_client.decision_payloads),
            "terminal_events": sum(event.name is AgentEventName.SESSION_CANCELLED for event in sink.events),
        }

print(json.dumps(anyio.run(recover), sort_keys=True))
"""
    child = subprocess.run(
        [sys.executable, "-c", script],
        check=True,
        capture_output=True,
        text=True,
        env={**os.environ, "TRD313_SESSION_ID": session_id},
    )
    recovered = json.loads(child.stdout)
    assert recovered == {
        "status": "cancelled",
        "branch_id": branch_id,
        "receipt_uri": receipt_uri,
        "replay_status": "cancelled",
        "retry_status": "cancelled",
        "model_calls": 0,
        "decision_writes": 0,
        "terminal_events": 0,
    }
    assert sum(
        event.name is AgentEventName.SESSION_CANCELLED
        for event in first_sink.events
    ) == 1
