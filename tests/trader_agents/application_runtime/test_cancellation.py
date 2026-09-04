"""Lifecycle contract for application-owned Agent session cancellation.

Subject: Runtime cancellation authority, canonical receipt recording, terminal state, and replay safety.
Level: In-process application workflow.
Collaborators: Real application runtime and Coordinator graph with in-memory checkpointing, static models, and MCP doubles.
Guarantees: Only a valid cancellation becomes terminal and repeated lifecycle calls cannot duplicate canonical mutation.
Non-goals: Postgres recovery, provider behavior, live MCP transport, and operator user-interface concerns."""

from __future__ import annotations
from collections.abc import Mapping
from typing import Any
import anyio
from langgraph.checkpoint.memory import InMemorySaver
from trader_agents import (
    AgentEventEmitter,
    AgentEventName,
    AgenticResearchRuntime,
    DataResearchAgent,
    OperatorCancellation,
    RecordingObservabilityEventSink,
    RecordingTraceSink,
    ResearchCoordinator,
    StaticJsonLlmClient,
    StrategyEngineeringAgent,
    StructuredModelRunner,
    development_model_profiles,
    first_slice_programs,
    first_slice_tool_catalogue,
)
from tests.trader_agents.support.coordinator_runtime import _CoordinatorMcpClient
from tests.trader_agents.support.data_runtime import _DataLoopMcpClient
from tests.trader_agents.support.runtime_contracts import _evidence_payload, _session
from tests.trader_agents.support.strategy_runtime import _StrategyLoopMcpClient


def test_runtime_cancellation_is_terminal_canonical_and_replay_safe() -> None:
    """The owning operator can cancel an interrupted session exactly once."""
    session = _session(session_id="session-runtime-cancellation")
    session_ref = _evidence_payload(
        "research_session",
        session.session_id,
        domain_owner="Orchestration",
    )
    responses = (
        {
            "objective_summary": "A material strategy rule is unspecified.",
            "material_ambiguities": ["Define the missing material rule."],
            "tasks": [],
        },
        {
            "action": "ask_operator",
            "summary": "The session requires operator clarification.",
            "reviewed_delegation_ids": [],
            "cited_evidence_refs": [],
            "criteria_applied": ["do not invent material semantics"],
            "affected_task_ids": [],
            "operator_question": "Provide or decline the missing material rule.",
            "blockers": [],
            "permitted_next_actions": ["answer or cancel"],
        },
    )
    model = StaticJsonLlmClient(responses)
    catalogue = first_slice_tool_catalogue()
    programs = first_slice_programs()
    profiles = development_model_profiles()
    traces = RecordingTraceSink()
    mcp = _CoordinatorMcpClient(session_ref=session_ref, artifacts={})
    coordinator = ResearchCoordinator(
        model_runner=StructuredModelRunner(model, trace_sink=traces),
        mcp_client=mcp,
        data_agent=DataResearchAgent(
            model_runner=StructuredModelRunner(StaticJsonLlmClient(())),
            mcp_client=_DataLoopMcpClient({}, {}),
            tool_catalogue=catalogue,
        ),
        strategy_agent=StrategyEngineeringAgent(
            model_runner=StructuredModelRunner(StaticJsonLlmClient(())),
            mcp_client=_StrategyLoopMcpClient({}, {}),
            tool_catalogue=catalogue,
        ),
        tool_catalogue=catalogue,
        programs=programs,
        model_profiles=profiles,
        trace_sink=traces,
    )
    lifecycle_sink = RecordingObservabilityEventSink()
    lifecycle_emitter = AgentEventEmitter(
        sink=lifecycle_sink,
        process_instance_id="runtime-lifecycle-process",
    )
    runtime = AgenticResearchRuntime(
        coordinator=coordinator,
        checkpointer=InMemorySaver(),
        tool_catalogue=catalogue,
        programs=programs,
        model_profiles=profiles,
        trace_sink=traces,
        event_emitter=lifecycle_emitter,
    )

    async def _run() -> tuple[Any, Any, Any, Mapping[str, Any]]:
        interrupted = await runtime.start(session)
        cancelled = await runtime.cancel(
            session,
            OperatorCancellation(
                operator_id=session.operator_id,
                reason="Stop this session before any further research work.",
            ),
        )
        replayed = await runtime.start(session)
        inspected = await runtime.inspect(session)
        return interrupted, cancelled, replayed, inspected

    interrupted, cancelled, replayed, inspected = anyio.run(_run)

    assert interrupted.kind == "operator_clarification_required"
    assert cancelled.status == "cancelled"
    assert cancelled.decision.blockers[0].code == "operator_cancelled"
    assert replayed == cancelled
    assert inspected["status"] == "cancelled"
    assert inspected["pending_interrupt"] == {}
    assert len(model.requests) == 2
    assert len(mcp.decision_payloads) == 2
    assert mcp.decision_payloads[-1]["status"] == "cancelled"
    lifecycle_names = [
        span["name"]
        for span in traces.spans
        if span["name"].startswith("agent.session.")
    ]
    assert lifecycle_names == [
        "agent.session.start",
        "agent.session.cancel",
        "agent.session.start",
        "agent.session.inspect",
    ]
    process_ids = {
        span["attributes"]["trader.process_instance_id"]
        for span in traces.spans
        if span["name"].startswith("agent.session.")
    }
    assert len(process_ids) == 1
    assert len(next(iter(process_ids))) == 32
    semantic_lifecycle_names = [event.name for event in lifecycle_sink.events]
    assert AgentEventName.SESSION_STARTED in semantic_lifecycle_names
    assert AgentEventName.SESSION_INTERRUPTED in semantic_lifecycle_names
    assert AgentEventName.SESSION_CANCELLED in semantic_lifecycle_names
    assert AgentEventName.SESSION_RESUMED in semantic_lifecycle_names
    assert AgentEventName.SESSION_INSPECTED in semantic_lifecycle_names
    assert AgentEventName.CHECKPOINT_SAVED in semantic_lifecycle_names
    assert AgentEventName.CHECKPOINT_RECOVERED in semantic_lifecycle_names
