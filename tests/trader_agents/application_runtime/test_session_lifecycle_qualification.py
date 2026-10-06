"""Qualification of governed session lifecycle and concurrent identity isolation.

Subject: Runtime checkpoint admission, command transitions, replay, and session isolation.
Level: In-process application workflow qualification.
Collaborators: Real Coordinator graph and shared in-memory LangGraph saver with
static models and MCP doubles; fresh runtime objects simulate worker replacement.
Guarantees: Commands fail closed before creation, recovery validates exact pins,
terminal replay does not duplicate public terminal events or canonical receipts,
and concurrent sessions retain separate checkpoint, budget, and terminal lineage.
Non-goals: PostgreSQL transport, cross-process writer exclusion, live model quality,
and Console HTTP authorization.
"""

from __future__ import annotations

import asyncio
from dataclasses import replace
from typing import Any

import anyio
from langgraph.checkpoint.memory import InMemorySaver
import pytest

from tests.trader_agents.application_runtime.test_interrupt import _runtime
from trader_agents import (
    AgentEventEmitter,
    AgentEventName,
    OperatorCancellation,
    OperatorInterruption,
    OperatorResponse,
    RecordingObservabilityEventSink,
)


def test_commands_require_a_created_checkpoint_and_owner() -> None:
    """Uncreated sessions and foreign operators cannot acquire lifecycle authority."""
    runtime, session = _runtime("session-lifecycle-uncreated")

    async def _run() -> None:
        with pytest.raises(ValueError, match="no operational checkpoint"):
            await runtime.inspect(session)
        with pytest.raises(ValueError, match="no operational checkpoint"):
            await runtime.resume(session, _response(session.operator_id))
        with pytest.raises(ValueError, match="no operational checkpoint"):
            await runtime.interrupt(session, _interruption(session.operator_id))
        with pytest.raises(ValueError, match="no operational checkpoint"):
            await runtime.cancel(session, _cancellation(session.operator_id))
        with pytest.raises(ValueError, match="operator response identity"):
            await runtime.resume(session, _response("foreign-operator"))
        with pytest.raises(ValueError, match="operator interruption identity"):
            await runtime.interrupt(session, _interruption("foreign-operator"))
        with pytest.raises(ValueError, match="operator cancellation identity"):
            await runtime.cancel(session, _cancellation("foreign-operator"))

    anyio.run(_run)


def test_lost_terminal_response_recovers_without_duplicate_event_or_receipt() -> None:
    """Fresh runtime inspection and replay expose one persisted cancellation."""
    runtime, session = _runtime("session-lifecycle-lost-response")
    sink = RecordingObservabilityEventSink()
    runtime.event_emitter = AgentEventEmitter(sink=sink, process_instance_id="first-worker")
    mcp = runtime.coordinator.mcp_client

    async def _run() -> tuple[dict[str, Any], object, object]:
        await runtime.start(session)
        await runtime.cancel(session, _cancellation(session.operator_id))
        # The caller loses the cancellation response after the checkpoint and
        # canonical receipt have committed; a new worker opens the same saver.
        recovered = replace(
            runtime,
            event_emitter=AgentEventEmitter(
                sink=sink, process_instance_id="replacement-worker"
            ),
        )
        state = await recovered.inspect(session)
        replay = await recovered.start(session)
        cancel_retry = await recovered.cancel(
            session, _cancellation(session.operator_id)
        )
        return state, replay, cancel_retry

    state, replay, cancel_retry = anyio.run(_run)
    assert state["status"] == "cancelled"
    assert state["pending_interrupt"] == {}
    assert state["terminal_result"]["status"] == "cancelled"
    assert state["decision_receipt_ref"]["uri"]
    assert replay == cancel_retry
    assert replay.status == "cancelled"
    assert len(mcp.decision_payloads) == 2  # interrupt plus cancellation
    assert sum(event.name is AgentEventName.SESSION_CANCELLED for event in sink.events) == 1


def test_recovered_checkpoint_rejects_changed_session_and_foreign_root() -> None:
    """Terminal replay and inspection validate identity before returning data."""
    runtime, session = _runtime("session-lifecycle-exact-pins")

    async def _run() -> None:
        await runtime.start(session)
        changed_authority = replace(session, operator_id="different-operator")
        for operation in (runtime.inspect, runtime.start):
            with pytest.raises(ValueError, match="checkpoint session_digest"):
                await operation(changed_authority)

        graph = runtime.coordinator.build_graph(
            session=session, checkpointer=runtime.checkpointer
        )
        config = {
            "configurable": {
                "thread_id": f"agent-session:{session.session_id}:coordinator"
            }
        }
        await graph.aupdate_state(
            config,
            {"branch_id": "foreign-root-branch"},
            as_node="commit_decision",
        )
        with pytest.raises(ValueError, match="checkpoint branch_id"):
            await runtime.inspect(session)

    anyio.run(_run)


def test_resume_requires_pending_interrupt_and_preserves_operator_boundary() -> None:
    """An owned response advances a real interrupt; repeats remain bounded."""
    runtime, session = _runtime("session-lifecycle-resume")

    async def _run() -> tuple[object, object, dict[str, Any]]:
        first = await runtime.start(session)
        with pytest.raises(ValueError, match="operator response identity"):
            await runtime.resume(session, _response("foreign-operator"))
        resumed = await replace(runtime).resume(
            session, _response(session.operator_id)
        )
        state = await runtime.inspect(session)
        return first, resumed, state

    first, resumed, state = anyio.run(_run)
    assert first.kind == "operator_clarification_required"
    assert resumed.status == "blocked"
    assert state["session_id"] == session.session_id
    assert state["pending_interrupt"] == {}
    assert state["terminal_result"]["status"] == "blocked"
    assert state["operator_response"] == {}


def test_foreign_terminal_lineage_is_rejected_before_public_read() -> None:
    """A top-level matching checkpoint cannot expose another session's result."""
    runtime, session = _runtime("session-lifecycle-terminal-lineage")

    async def _run() -> None:
        await runtime.start(session)
        await runtime.cancel(session, _cancellation(session.operator_id))
        graph = runtime.coordinator.build_graph(
            session=session, checkpointer=runtime.checkpointer
        )
        config = {
            "configurable": {
                "thread_id": f"agent-session:{session.session_id}:coordinator"
            }
        }
        snapshot = await graph.aget_state(config)
        terminal = dict(snapshot.values["terminal_result"])
        terminal["session_id"] = "foreign-session"
        await graph.aupdate_state(
            config, {"terminal_result": terminal}, as_node="commit_decision"
        )
        with pytest.raises(ValueError, match="terminal result belongs to another"):
            await runtime.inspect(session)
        with pytest.raises(ValueError, match="terminal result belongs to another"):
            await runtime.start(session)

    anyio.run(_run)


def test_concurrent_sessions_keep_checkpoint_budget_and_terminal_lineage() -> None:
    """Two sessions sharing one saver cannot inherit each other's state."""
    first, session_a = _runtime("session-lifecycle-a")
    second, session_b = _runtime("session-lifecycle-b")
    shared = InMemorySaver()
    first.checkpointer = shared
    second.checkpointer = shared

    async def _run() -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
        await asyncio.gather(first.start(session_a), second.start(session_b))
        await first.cancel(session_a, _cancellation(session_a.operator_id))
        state_a, state_b = await asyncio.gather(
            first.inspect(session_a), second.inspect(session_b)
        )
        await second.resume(session_b, _response(session_b.operator_id))
        state_b_after = await second.inspect(session_b)
        state_a_after = await first.inspect(session_a)
        return state_a, state_b, state_b_after, state_a_after

    state_a, state_b, state_b_after, state_a_after = anyio.run(_run)
    assert state_a["session_id"] == session_a.session_id
    assert state_b["session_id"] == session_b.session_id
    assert state_a["branch_id"] != state_b["branch_id"]
    assert state_a["status"] == "cancelled"
    assert state_a["decision_receipt_ref"]["uri"]
    assert state_b["status"] == "awaiting_operator"
    assert state_b["decision_receipt_ref"]["uri"]
    assert state_b["decision_receipt_ref"] != state_a["decision_receipt_ref"]
    assert state_b_after["status"] == "blocked"
    assert state_b_after["pending_interrupt"] == {}
    assert state_a_after == state_a
    assert state_a["terminal_result"] != state_b_after["terminal_result"]


def _response(operator_id: str) -> OperatorResponse:
    """Construct one bounded operator response."""
    return OperatorResponse(
        approved=False, answer="Stop and review.", operator_id=operator_id
    )


def _interruption(operator_id: str) -> OperatorInterruption:
    """Construct one bounded operator interruption."""
    return OperatorInterruption(operator_id=operator_id, reason="Review this session.")


def _cancellation(operator_id: str) -> OperatorCancellation:
    """Construct one bounded operator cancellation."""
    return OperatorCancellation(operator_id=operator_id, reason="Stop this session.")
