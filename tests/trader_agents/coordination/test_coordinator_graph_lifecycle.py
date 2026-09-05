"""Lifecycle contracts for the Research Coordinator graph.

Subject: Parallel specialist dispatch, hard joins, evidence verification, interrupts, and canonical decision reconciliation.
Level: In-process coordination workflow.
Collaborators: Real Coordinator, specialist graphs, and in-memory checkpointing with static models and MCP doubles.
Guarantees: Shared state has one writer, selected evidence is reviewed, and recovery neither loses nor duplicates decisions.
Non-goals: Postgres checkpoint transport, live models, real MCP transport, application cancellation, and release qualification."""

from __future__ import annotations
import asyncio
from collections.abc import Mapping, Sequence
from typing import Any
import anyio
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command
import pytest
from trader_agents import (
    AgenticSliceResult,
    CanonicalEvidenceRef,
    DataResearchAgent,
    RecordingTraceSink,
    ResearchCoordinator,
    StaticJsonLlmClient,
    StrategyEngineeringAgent,
    StructuredModelRunner,
    build_agent_checkpoint_state,
    build_delegation,
    coordinator_thread_config,
    development_model_profiles,
    first_slice_programs,
    first_slice_tool_catalogue,
    strategy_build_contract_from_session,
)
from trader_research.foundation import stable_research_id
from tests.trader_agents.support.coordinator_runtime import _CoordinatorMcpClient
from tests.trader_agents.support.data_runtime import _DataLoopMcpClient
from tests.trader_agents.support.runtime_contracts import (
    _data_tool_turn,
    _evidence_payload,
    _session,
    _strategy_tool_turn,
    _task,
)
from tests.trader_agents.support.strategy_runtime import _StrategyLoopMcpClient


def test_coordinator_graph_parallel_joins_verifies_and_concludes() -> None:
    """Both specialists rejoin one writer before a grounded conclusion."""
    session = _session()
    session_ref = _evidence_payload(
        "research_session",
        session.session_id,
        domain_owner="Orchestration",
    )
    manifest_ref = _evidence_payload("dataset_manifest", "manifest-1")
    quality_ref = _evidence_payload("data_quality_report", "quality-1")
    implementation_ref = _evidence_payload(
        "implementation_version",
        "implementation-1",
        domain_owner="Experiments",
    )
    validation_ref = _evidence_payload(
        "implementation_validation_report",
        "validation-1",
        domain_owner="Experiments",
    )
    scope_arguments = {
        "symbols": ["BTC/USD", "ETH/USD"],
        "asset_class": "crypto",
        "timeframe": "1h",
        "start": "2024-01-01T00:00:00Z",
        "end": "2024-06-30T23:00:00Z",
    }
    data_responses = (
        _data_tool_turn("inventory", "data_get_inventory", scope_arguments),
        _data_tool_turn("quality", "data_summarize_quality", scope_arguments),
        {
            "action": "change_phase",
            "public_rationale": "Evidence can now be captured canonically.",
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
            mutation_reason="Capture exact Data evidence.",
        ),
        {
            "action": "return_result",
            "public_rationale": "The complete scope has exact snapshot evidence.",
            "final_conclusion": {
                "status": "ready",
                "answered_questions": ["Data is ready."],
                "findings": ["Both assets are covered."],
                "evidence_refs": [manifest_ref, quality_ref],
                "unresolved_questions": [],
                "assumptions": [],
                "uncertainty": [],
                "blockers": [],
                "advisory_next_actions": ["coordinator review"],
            },
        },
    )
    contract_branch = stable_research_id(
        "agent_branch",
        {"session_id": session.session_id, "task_id": "strategy"},
    )
    contract = strategy_build_contract_from_session(
        session,
        branch_id=contract_branch,
    )
    strategy_responses = (
        _strategy_tool_turn(
            "search",
            "research_search_implementations",
            {"query": "momentum", "implementation_kinds": ["strategy"]},
        ),
        _strategy_tool_turn(
            "get",
            "research_get_implementation",
            {"implementation_ref": implementation_ref["uri"]},
        ),
        _strategy_tool_turn(
            "compare",
            "research_compare_implementation",
            {
                "implementation_ref": implementation_ref["uri"],
                "build_contract": contract.model_dump(mode="json"),
            },
        ),
        {
            "action": "choose_build",
            "public_rationale": "The admitted candidate is an exact match.",
            "build_decision": "reuse",
        },
        {
            "action": "return_result",
            "public_rationale": "Reuse is supported by exact admission evidence.",
            "final_conclusion": {
                "status": "ready",
                "answered_questions": ["The implementation is reusable."],
                "findings": ["All compared fields match."],
                "evidence_refs": [implementation_ref, validation_ref],
                "unresolved_questions": [],
                "assumptions": [],
                "uncertainty": [],
                "blockers": [],
                "advisory_next_actions": ["coordinator review"],
            },
        },
    )
    agenda = {
        "objective_summary": "Prepare exact Data and admitted implementation evidence.",
        "material_ambiguities": [],
        "tasks": [
            _task(
                "data",
                "data_research",
                mutation_requested=True,
            ).model_dump(mode="json"),
            _task(
                "strategy",
                "strategy_engineering",
                mutation_requested=True,
            ).model_dump(mode="json"),
        ],
    }
    data_branch = stable_research_id(
        "agent_branch",
        {"session_id": session.session_id, "task_id": "data"},
    )
    required_refs = [
        CanonicalEvidenceRef.model_validate(session_ref),
    ]
    data_delegation = build_delegation(
        session_id=session.session_id,
        branch_id=data_branch,
        task=_task("data", "data_research", mutation_requested=True),
        required_input_refs=required_refs,
        permitted_side_effects=["read_only", "local_mutating"],
        reserved_model_calls=5,
        reserved_tool_calls=11,
        reserved_tokens=6_000,
        attempt=1,
    )
    strategy_delegation = build_delegation(
        session_id=session.session_id,
        branch_id=contract_branch,
        task=_task("strategy", "strategy_engineering", mutation_requested=True),
        required_input_refs=required_refs,
        permitted_side_effects=["read_only", "local_mutating"],
        reserved_model_calls=5,
        reserved_tool_calls=11,
        reserved_tokens=6_000,
        attempt=1,
    )
    conclusion = {
        "action": "conclude",
        "summary": "Data is ready and one exact admitted implementation is reusable.",
        "reviewed_delegation_ids": [
            data_delegation.delegation_id,
            strategy_delegation.delegation_id,
        ],
        "cited_evidence_refs": [
            manifest_ref,
            quality_ref,
            implementation_ref,
            validation_ref,
        ],
        "criteria_applied": [
            "complete Data readiness",
            "independent implementation admission",
        ],
        "affected_task_ids": ["data", "strategy"],
        "blockers": [],
        "permitted_next_actions": ["hand off to Experiment Design"],
    }
    coordinator_client = StaticJsonLlmClient((agenda, conclusion))
    traces = RecordingTraceSink()
    catalogue = first_slice_tool_catalogue()
    programs = first_slice_programs()
    profiles = development_model_profiles()
    coordinator_mcp = _CoordinatorMcpClient(
        session_ref=session_ref,
        artifacts={
            reference["uri"]: reference
            for reference in (
                manifest_ref,
                quality_ref,
                implementation_ref,
                validation_ref,
            )
        },
    )
    coordinator = ResearchCoordinator(
        model_runner=StructuredModelRunner(
            coordinator_client,
            trace_sink=traces,
        ),
        mcp_client=coordinator_mcp,
        data_agent=DataResearchAgent(
            model_runner=StructuredModelRunner(
                StaticJsonLlmClient(data_responses),
                trace_sink=traces,
            ),
            mcp_client=_DataLoopMcpClient(manifest_ref, quality_ref),
            tool_catalogue=catalogue,
            trace_sink=traces,
        ),
        strategy_agent=StrategyEngineeringAgent(
            model_runner=StructuredModelRunner(
                StaticJsonLlmClient(strategy_responses),
                trace_sink=traces,
            ),
            mcp_client=_StrategyLoopMcpClient(
                implementation_ref,
                validation_ref,
            ),
            tool_catalogue=catalogue,
            trace_sink=traces,
        ),
        tool_catalogue=catalogue,
        programs=programs,
        model_profiles=profiles,
        trace_sink=traces,
    )
    initial = build_agent_checkpoint_state(
        session_id=session.session_id,
        session_digest=session.session_digest,
        branch_id="root",
        coordinator_program_id="research-coordinator-v7",
        model_profile_id=session.model_profile_id,
        tool_catalog_id=catalogue.catalogue_id,
    )
    graph = coordinator.build_graph(
        session=session,
        checkpointer=InMemorySaver(),
    )

    async def _run() -> Any:
        return await graph.ainvoke(
            initial,
            coordinator_thread_config(session.session_id),
        )

    output = anyio.run(_run)
    result = AgenticSliceResult.model_validate(output["terminal_result"])
    assert result.status == "completed"
    assert result.data_return is not None
    assert result.strategy_return is not None
    assert result.budget_used.model_calls == 12
    assert len(coordinator_client.requests) == 2
    assert coordinator_mcp.read_calls == 4
    assert "agent.coordinator.commit_decision" in {
        span["name"] for span in traces.spans
    }
    span_names = {span["name"] for span in traces.spans}
    assert {
        "agent.model.research_coordinator",
        "agent.model.data_research",
        "agent.model.strategy_engineering",
        "agent.mcp.data_get_inventory",
        "agent.mcp_result.data_get_inventory",
        "agent.mcp.research_search_implementations",
        "agent.mcp_result.research_search_implementations",
        "agent.mcp.research_read_artifact",
        "agent.mcp_result.research_read_artifact",
        "agent.coordinator.commit_decision",
    }.issubset(span_names)
    assert all(
        span["attributes"]["trader.session_id"] == session.session_id
        for span in traces.spans
    )
    assert all("prompt" not in str(span) for span in traces.spans)


def test_coordinator_interrupt_resumes_with_a_fresh_graph_instance() -> None:
    """A bounded operator answer resumes the checkpointed coordinator thread."""
    session = _session()
    session_ref = _evidence_payload(
        "research_session",
        session.session_id,
        domain_owner="Orchestration",
    )
    ambiguous_agenda = {
        "objective_summary": "The material allocation rule is unspecified.",
        "material_ambiguities": ["Define how ties between assets are resolved."],
        "tasks": [],
    }
    ask = {
        "action": "ask_operator",
        "summary": "The build contract omits a material tie-breaking rule.",
        "reviewed_delegation_ids": [],
        "cited_evidence_refs": [],
        "criteria_applied": ["no invented strategy semantics"],
        "affected_task_ids": [],
        "operator_question": "Should the session stop because no approved tie rule exists?",
        "blockers": [],
        "permitted_next_actions": ["answer the clarification"],
    }
    stop = {
        "action": "stop_fail_closed",
        "summary": "The operator declined to add a material rule to this session.",
        "reviewed_delegation_ids": [],
        "cited_evidence_refs": [],
        "criteria_applied": ["immutable session authority"],
        "affected_task_ids": [],
        "blockers": [
            {
                "code": "material_rule_unapproved",
                "message": "A new approved session is required to add the rule.",
            }
        ],
        "permitted_next_actions": ["create a corrected research session"],
    }
    catalogue = first_slice_tool_catalogue()
    programs = first_slice_programs()
    profiles = development_model_profiles()
    saver = InMemorySaver()
    coordinator_mcp = _CoordinatorMcpClient(
        session_ref=session_ref,
        artifacts={},
    )

    def _coordinator(responses: Sequence[Mapping[str, Any]]) -> ResearchCoordinator:
        """Build a fresh coordinator process around the shared checkpointer."""
        inert_data = DataResearchAgent(
            model_runner=StructuredModelRunner(StaticJsonLlmClient(())),
            mcp_client=_DataLoopMcpClient({}, {}),
            tool_catalogue=catalogue,
        )
        inert_strategy = StrategyEngineeringAgent(
            model_runner=StructuredModelRunner(StaticJsonLlmClient(())),
            mcp_client=_StrategyLoopMcpClient({}, {}),
            tool_catalogue=catalogue,
        )
        return ResearchCoordinator(
            model_runner=StructuredModelRunner(StaticJsonLlmClient(responses)),
            mcp_client=coordinator_mcp,
            data_agent=inert_data,
            strategy_agent=inert_strategy,
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

    async def _run() -> tuple[Mapping[str, Any], Mapping[str, Any]]:
        first_graph = _coordinator((ambiguous_agenda, ask)).build_graph(
            session=session,
            checkpointer=saver,
        )
        interrupted = await first_graph.ainvoke(initial, config)
        second_graph = _coordinator((ambiguous_agenda, stop)).build_graph(
            session=session,
            checkpointer=saver,
        )
        resumed = await second_graph.ainvoke(
            Command(
                resume={
                    "approved": False,
                    "answer": "Stop; do not invent or add a tie rule.",
                    "operator_id": session.operator_id,
                }
            ),
            config,
        )
        return interrupted, resumed

    interrupted, resumed = anyio.run(_run)
    assert interrupted["status"] == "awaiting_operator"
    assert interrupted["__interrupt__"]
    result = AgenticSliceResult.model_validate(resumed["terminal_result"])
    assert result.status == "blocked"
    assert result.decision.action.value == "stop_fail_closed"


def test_coordinator_replays_checkpointed_decision_after_lost_receipt_response() -> (
    None
):
    """A canonical receipt retry cannot trigger a second model decision."""
    session = _session(session_id="session-coordinator-receipt-recovery")
    session_ref = _evidence_payload(
        "research_session",
        session.session_id,
        domain_owner="Orchestration",
    )
    ambiguous_agenda = {
        "objective_summary": "A material strategy rule is unspecified.",
        "material_ambiguities": ["Define the missing material rule."],
        "tasks": [],
    }
    ask = {
        "action": "ask_operator",
        "summary": "The session cannot proceed without operator authority.",
        "reviewed_delegation_ids": [],
        "cited_evidence_refs": [],
        "criteria_applied": ["do not invent material semantics"],
        "affected_task_ids": [],
        "operator_question": "Provide or decline the missing material rule.",
        "blockers": [],
        "permitted_next_actions": ["answer the clarification"],
    }
    model = StaticJsonLlmClient((ambiguous_agenda, ask))
    catalogue = first_slice_tool_catalogue()
    programs = first_slice_programs()
    profiles = development_model_profiles()
    mcp = _CoordinatorMcpClient(
        session_ref=session_ref,
        artifacts={},
        interrupt_decision_once=True,
    )
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
    saver = InMemorySaver()
    config = coordinator_thread_config(session.session_id)
    initial = build_agent_checkpoint_state(
        session_id=session.session_id,
        session_digest=session.session_digest,
        branch_id="root",
        coordinator_program_id="research-coordinator-v7",
        model_profile_id=session.model_profile_id,
        tool_catalog_id=catalogue.catalogue_id,
    )

    async def _run() -> tuple[Mapping[str, Any], Any]:
        first_graph = coordinator.build_graph(
            session=session,
            checkpointer=saver,
        )
        with pytest.raises(asyncio.CancelledError):
            await first_graph.ainvoke(initial, config)
        recovered_graph = coordinator.build_graph(
            session=session,
            checkpointer=saver,
        )
        output = await recovered_graph.ainvoke(None, config)
        return output, await recovered_graph.aget_state(config)

    output, snapshot = anyio.run(_run)

    assert output["status"] == "awaiting_operator"
    assert snapshot.interrupts
    assert len(model.requests) == 2
    assert len(mcp.decision_payloads) == 2
    assert mcp.decision_payloads[0] == mcp.decision_payloads[1]
