"""PostgreSQL integration tests for fresh-process-equivalent Agent recovery.

Subject: Agent checkpoint durability and idempotent Data and Coordinator continuation across independent connections.
Level: PostgreSQL adapter integration.
Collaborators: Real LangGraph PostgreSQL savers with static models and deterministic in-memory MCP doubles.
Guarantees: Accepted tool work and checkpointed coordinator decisions survive connection replacement without duplicate mutation.
Non-goals: Canonical research-store qualification, live models, real MCP transport, process crashes, and bounded scale."""

from __future__ import annotations
import asyncio
from collections.abc import Mapping
import os
from typing import Any
from uuid import uuid4
import anyio
import pytest
from trader_agents import (
    AgentRole,
    DataResearchAgent,
    ResearchCoordinator,
    SpecialistReturn,
    StaticJsonLlmClient,
    StrategyEngineeringAgent,
    StructuredModelRunner,
    build_agent_checkpoint_state,
    build_delegation,
    composite_data_scope_from_session,
    coordinator_thread_config,
    development_model_profiles,
    first_slice_programs,
    first_slice_tool_catalogue,
    open_postgres_checkpointer,
)
from tests.trader_agents.support.coordinator_runtime import _CoordinatorMcpClient
from tests.trader_agents.support.data_runtime import _DataLoopMcpClient
from tests.trader_agents.support.runtime_contracts import (
    _data_tool_turn,
    _evidence_payload,
    _session,
    _task,
)
from tests.trader_agents.support.runtime_faults import _InterruptingJsonLlmClient
from tests.trader_agents.support.strategy_runtime import _StrategyLoopMcpClient


@pytest.mark.postgres
def test_data_specialist_recovers_across_fresh_postgres_connections() -> None:
    """Postgres recovery survives new saver, graph, agent, and model objects."""
    dsn = str(os.environ.get("TRADER_AGENTS_CHECKPOINT_DSN") or "").strip()
    if not dsn:
        pytest.skip("TRADER_AGENTS_CHECKPOINT_DSN is required")
    session = _session(session_id=f"session-pg-recovery-{uuid4().hex}")
    scope = composite_data_scope_from_session(session)
    delegation = build_delegation(
        session_id=session.session_id,
        branch_id="data-postgres-recovery",
        task=_task("data-postgres-recovery", "data_research"),
        required_input_refs=[],
        permitted_side_effects=["read_only", "local_mutating"],
        reserved_model_calls=6,
        reserved_tool_calls=10,
        reserved_tokens=6_000,
        attempt=1,
    )
    scope_arguments = {
        "symbols": ["BTC/USD", "ETH/USD"],
        "asset_class": "crypto",
        "timeframe": "1h",
        "start": "2024-01-01T00:00:00Z",
        "end": "2024-06-30T23:00:00Z",
    }
    manifest_ref = _evidence_payload("dataset_manifest", "pg-manifest")
    quality_ref = _evidence_payload("data_quality_report", "pg-quality")
    calls: list[str] = []
    catalogue = first_slice_tool_catalogue()
    program = first_slice_programs().for_role(AgentRole.DATA_RESEARCH)
    profile = development_model_profiles().get(program.model_profile_id)

    async def _run() -> SpecialistReturn:
        async with open_postgres_checkpointer(dsn=dsn, setup=True) as first_saver:
            first_agent = DataResearchAgent(
                model_runner=StructuredModelRunner(
                    _InterruptingJsonLlmClient(
                        (
                            _data_tool_turn(
                                "inventory",
                                "data_get_inventory",
                                scope_arguments,
                            ),
                        )
                    )
                ),
                mcp_client=_DataLoopMcpClient(
                    manifest_ref,
                    quality_ref,
                    calls=calls,
                ),
                tool_catalogue=catalogue,
            )
            with pytest.raises(asyncio.CancelledError):
                await first_agent.run(
                    session=session,
                    delegation=delegation,
                    scope=scope,
                    program=program,
                    profile=profile,
                    checkpointer=first_saver,
                )

        remaining = (
            _data_tool_turn("quality", "data_summarize_quality", scope_arguments),
            {
                "action": "change_phase",
                "public_rationale": "The exact scope can now be captured.",
                "next_phase": "review",
            },
            _data_tool_turn(
                "snapshot",
                "data_create_research_snapshot",
                {
                    **scope_arguments,
                    "requested_by": session.session_id,
                    "actor": "Data Research Agent",
                },
                mutation_reason="Capture exact Postgres recovery evidence.",
            ),
            {
                "action": "return_result",
                "public_rationale": "The recovered scope has exact evidence.",
                "final_conclusion": {
                    "status": "ready",
                    "answered_questions": ["The requested Data is ready."],
                    "findings": ["Fresh-process recovery retained inventory."],
                    "evidence_refs": [manifest_ref, quality_ref],
                    "unresolved_questions": [],
                    "assumptions": [],
                    "uncertainty": [],
                    "blockers": [],
                    "advisory_next_actions": ["coordinator review"],
                },
            },
        )
        async with open_postgres_checkpointer(dsn=dsn) as recovered_saver:
            recovered_agent = DataResearchAgent(
                model_runner=StructuredModelRunner(StaticJsonLlmClient(remaining)),
                mcp_client=_DataLoopMcpClient(
                    manifest_ref,
                    quality_ref,
                    calls=calls,
                ),
                tool_catalogue=catalogue,
            )
            return await recovered_agent.run(
                session=session,
                delegation=delegation,
                scope=scope,
                program=program,
                profile=profile,
                checkpointer=recovered_saver,
            )

    result = anyio.run(_run)
    assert result.status.value == "ready"
    assert calls == [
        "data_get_inventory",
        "data_summarize_quality",
        "data_create_research_snapshot",
    ]


@pytest.mark.postgres
def test_coordinator_recovers_checkpointed_decision_across_postgres_connections() -> (
    None
):
    """A fresh coordinator commits the exact pre-crash decision without LLM use."""
    dsn = str(os.environ.get("TRADER_AGENTS_CHECKPOINT_DSN") or "").strip()
    if not dsn:
        pytest.skip("TRADER_AGENTS_CHECKPOINT_DSN is required")
    session = _session(session_id=f"session-pg-coordinator-{uuid4().hex}")
    session_ref = _evidence_payload(
        "research_session",
        session.session_id,
        domain_owner="Orchestration",
    )
    agenda = {
        "objective_summary": "A material strategy rule is unspecified.",
        "material_ambiguities": ["Define the missing material rule."],
        "tasks": [],
    }
    decision = {
        "action": "ask_operator",
        "summary": "The session requires operator clarification.",
        "reviewed_delegation_ids": [],
        "cited_evidence_refs": [],
        "criteria_applied": ["do not invent material semantics"],
        "affected_task_ids": [],
        "operator_question": "Provide or decline the missing material rule.",
        "blockers": [],
        "permitted_next_actions": ["answer the clarification"],
    }
    catalogue = first_slice_tool_catalogue()
    programs = first_slice_programs()
    profiles = development_model_profiles()
    decision_payloads: list[dict[str, Any]] = []
    first_model = StaticJsonLlmClient((agenda, decision))
    recovered_model = StaticJsonLlmClient(())

    def _coordinator(
        model: StaticJsonLlmClient,
        mcp: _CoordinatorMcpClient,
    ) -> ResearchCoordinator:
        return ResearchCoordinator(
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

    initial = build_agent_checkpoint_state(
        session_id=session.session_id,
        session_digest=session.session_digest,
        branch_id="root",
        coordinator_program_id="research-coordinator-v7",
        model_profile_id=session.model_profile_id,
        tool_catalog_id=catalogue.catalogue_id,
    )
    config = coordinator_thread_config(session.session_id)

    async def _run() -> tuple[Mapping[str, Any], int]:
        first_mcp = _CoordinatorMcpClient(
            session_ref=session_ref,
            artifacts={},
            interrupt_decision_once=True,
            decision_payloads=decision_payloads,
        )
        async with open_postgres_checkpointer(dsn=dsn, setup=True) as first_saver:
            first_graph = _coordinator(first_model, first_mcp).build_graph(
                session=session,
                checkpointer=first_saver,
            )
            with pytest.raises(asyncio.CancelledError):
                await first_graph.ainvoke(initial, config)

        recovered_mcp = _CoordinatorMcpClient(
            session_ref=session_ref,
            artifacts={},
            decision_payloads=decision_payloads,
        )
        async with open_postgres_checkpointer(dsn=dsn) as recovered_saver:
            recovered_graph = _coordinator(
                recovered_model,
                recovered_mcp,
            ).build_graph(
                session=session,
                checkpointer=recovered_saver,
            )
            output = await recovered_graph.ainvoke(None, config)
        return output, len(recovered_model.requests)

    output, recovered_model_calls = anyio.run(_run)

    assert output["status"] == "awaiting_operator"
    assert recovered_model_calls == 0
    assert len(decision_payloads) == 2
    assert decision_payloads[0] == decision_payloads[1]
