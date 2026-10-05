"""Lifecycle contract for an owning operator pause and fresh-process resume.

Subject: Runtime interruption checkpoint boundary and replay-safe resume.
Level: In-process application workflow.
Collaborators: Real LangGraph runtime with an in-memory checkpointer and static MCP/model doubles.
Guarantees: A pause is represented by a public pending interrupt and can be resumed after the command boundary.
Non-goals: PostgreSQL command leasing, HTTP authority, provider execution, and hidden model state.
"""

from __future__ import annotations

import anyio
from dataclasses import replace
from langgraph.checkpoint.memory import InMemorySaver

from tests.trader_agents.application_runtime.test_cancellation import _session
from tests.trader_agents.support.coordinator_runtime import _CoordinatorMcpClient
from tests.trader_agents.support.data_runtime import _DataLoopMcpClient
from tests.trader_agents.support.runtime_contracts import _evidence_payload
from tests.trader_agents.support.strategy_runtime import _StrategyLoopMcpClient
from trader_agents import (
    AgentEventEmitter,
    AgenticResearchRuntime,
    DataResearchAgent,
    OperatorInterruption,
    OperatorResponse,
    ResearchCoordinator,
    StaticJsonLlmClient,
    StrategyEngineeringAgent,
    StructuredModelRunner,
    development_model_profiles,
    first_slice_programs,
    first_slice_tool_catalogue,
)


def _runtime(session_id: str) -> tuple[AgenticResearchRuntime, object]:
    """Build one real runtime over deterministic model and MCP doubles."""
    session = _session(session_id=session_id)
    session_ref = _evidence_payload(
        "research_session", session.session_id, domain_owner="Orchestration"
    )
    model = StaticJsonLlmClient(
        (
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
            {
                "objective_summary": "A material strategy rule remains unspecified.",
                "material_ambiguities": ["Define the missing material rule."],
                "tasks": [],
            },
            {
                "action": "ask_operator",
                "summary": "The session remains bounded by an operator decision.",
                "reviewed_delegation_ids": [],
                "cited_evidence_refs": [],
                "criteria_applied": ["remain fail closed"],
                "affected_task_ids": [],
                "operator_question": "Confirm the next bounded action.",
                "blockers": [],
                "permitted_next_actions": ["answer or cancel"],
            },
            {
                "action": "ask_operator",
                "summary": "The session remains bounded by an operator decision.",
                "reviewed_delegation_ids": [],
                "cited_evidence_refs": [],
                "criteria_applied": ["remain fail closed"],
                "affected_task_ids": [],
                "operator_question": "Confirm the next bounded action.",
                "blockers": [],
                "permitted_next_actions": ["answer or cancel"],
            },
        )
    )
    catalogue = first_slice_tool_catalogue()
    programs = first_slice_programs()
    profiles = development_model_profiles()
    mcp = _CoordinatorMcpClient(session_ref=session_ref, artifacts={})
    coordinator = ResearchCoordinator(
        model_runner=StructuredModelRunner(model),
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
    )
    return (
        AgenticResearchRuntime(
            coordinator=coordinator,
            checkpointer=InMemorySaver(),
            tool_catalogue=catalogue,
            programs=programs,
            model_profiles=profiles,
            event_emitter=AgentEventEmitter(),
        ),
        session,
    )


def test_runtime_interrupt_persists_public_pause_and_resumes() -> None:
    """A pause survives the command boundary and applies a typed response."""
    runtime, session = _runtime("session-runtime-interruption")

    async def _run() -> tuple[object, object, object, dict[str, object], int]:
        first = await runtime.start(session)
        graph = runtime.coordinator.build_graph(
            session=session,
            checkpointer=runtime.checkpointer,
        )
        config = {"configurable": {"thread_id": f"agent-session:{session.session_id}:coordinator"}}
        await graph.aupdate_state(
            config,
            {"pending_interrupt": {}, "status": "running", "phase": "interpret"},
            as_node="commit_decision",
        )
        paused = await runtime.interrupt(
            session,
            OperatorInterruption(
                operator_id=session.operator_id,
                reason="Review the public trajectory before continuing.",
            ),
        )
        recovered_runtime = replace(runtime)
        resumed = await recovered_runtime.resume(
            session,
            response=OperatorResponse(
                approved=False,
                answer="Stop and review the evidence.",
                operator_id=session.operator_id,
            ),
        )
        return (
            first,
            paused,
            resumed,
            dict(await recovered_runtime.inspect(session)),
            len(runtime.coordinator.model_runner.client.requests),
        )

    first, paused, resumed, inspected, model_calls = anyio.run(_run)
    assert getattr(first, "kind") == "operator_clarification_required"
    assert getattr(paused, "kind") == "operator_pause"
    assert getattr(resumed, "kind", None) != "operator_pause"
    assert model_calls >= 3
    assert inspected["pending_interrupt"] == {}
    assert inspected["status"] in {"awaiting_operator", "completed", "blocked", "failed"}
