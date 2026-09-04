"""Observable contract for the Coordinator-to-Data handoff.

Subject: One Coordinator delegation to the Data Research specialist and the resulting evidence review.
Level: Agent coordination contract.
Collaborators: In-memory LangGraph checkpointing, static model clients, recording/console event sinks, and package-owned MCP doubles.
Guarantees: A Data-only session returns canonical evidence through the Coordinator and emits a complete, ordered, correlated public trajectory.
Non-goals: Real model behavior, Postgres recovery, parallel scheduling, Strategy execution, or release qualification.
"""

from __future__ import annotations

import os
from dataclasses import replace

import anyio
from langgraph.checkpoint.memory import InMemorySaver

from trader_agents import (
    AgentEventEmitter,
    AgentEventLevel,
    AgentEventName,
    AgenticResearchRuntime,
    AgenticSliceResult,
    AgentRole,
    CanonicalEvidenceRef,
    CompositeObservabilityEventSink,
    ConsoleObservabilityEventSink,
    DataResearchAgent,
    RecordingObservabilityEventSink,
    ResearchCoordinator,
    StaticJsonLlmClient,
    StrategyEngineeringAgent,
    StructuredModelRunner,
    agent_console_config,
    build_delegation,
    development_model_profiles,
    first_slice_programs,
    first_slice_tool_catalogue,
)
from trader_research.foundation import stable_research_id

from tests.trader_agents.support.coordinator_runtime import _CoordinatorMcpClient
from tests.trader_agents.support.data_runtime import _DataLoopMcpClient
from tests.trader_agents.support.runtime_contracts import (
    _data_tool_turn,
    _evidence_payload,
    _session,
    _task,
)
from tests.trader_agents.support.strategy_runtime import _StrategyLoopMcpClient


def test_runtime_data_handoff_emits_correlated_observability_trajectory() -> None:
    """Prove one Data return is accepted before the Coordinator concludes.

    The runtime must delegate only to Data Research, obtain exact manifest and
    quality references, re-read both references at the Coordinator boundary,
    record one terminal decision, and leave Strategy Engineering untouched.
    The event assertions then prove that this functional handoff is exposed as
    one ordered, fully correlated public trajectory without warning or error.
    """
    session = replace(
        _session(session_id="session-data-only"),
        objective="Establish whether the approved multi-asset Data scope is ready.",
        success_definition="Return exact manifest and quality evidence.",
        approval_policy={"data_loading": "preapproved_within_scope"},
        implementation_specification=None,
        implementation_ref="research://implementation_version/existing-input",
    )
    session_ref = _evidence_payload(
        "research_session",
        session.session_id,
        domain_owner="Orchestration",
    )
    manifest_ref = _evidence_payload("dataset_manifest", "manifest-data-only")
    quality_ref = _evidence_payload(
        "data_quality_report",
        "quality-data-only",
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
            "public_rationale": "The readiness evidence can be captured canonically.",
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
            mutation_reason="Capture the exact readiness evidence.",
        ),
        {
            "action": "return_result",
            "public_rationale": "The approved scope has exact readiness evidence.",
            "final_conclusion": {
                "status": "ready",
                "answered_questions": ["The approved Data scope is ready."],
                "findings": ["Both requested assets have complete coverage."],
                "evidence_refs": [manifest_ref, quality_ref],
                "unresolved_questions": [],
                "assumptions": [],
                "uncertainty": [],
                "blockers": [],
                "advisory_next_actions": ["coordinator review"],
            },
        },
    )
    agenda_task = _task(
        "data-readiness",
        "data_research",
        mutation_requested=True,
    )
    agenda = {
        "objective_summary": "Establish readiness of the approved Data scope.",
        "material_ambiguities": [],
        "tasks": [agenda_task.model_dump(mode="json")],
    }
    data_branch = stable_research_id(
        "agent_branch",
        {"session_id": session.session_id, "task_id": agenda_task.task_id},
    )
    data_delegation = build_delegation(
        session_id=session.session_id,
        branch_id=data_branch,
        task=agenda_task,
        required_input_refs=[CanonicalEvidenceRef.model_validate(session_ref)],
        permitted_side_effects=["read_only", "local_mutating"],
        reserved_model_calls=5,
        reserved_tool_calls=11,
        reserved_tokens=6_000,
        attempt=1,
    )
    conclusion = {
        "action": "conclude",
        "summary": "The approved Data scope is ready for downstream research.",
        "reviewed_delegation_ids": [data_delegation.delegation_id],
        "cited_evidence_refs": [manifest_ref, quality_ref],
        "criteria_applied": ["complete coverage and canonical quality evidence"],
        "affected_task_ids": [agenda_task.task_id],
        "blockers": [],
        "permitted_next_actions": ["use the exact Data snapshot"],
    }
    coordinator_client = StaticJsonLlmClient((agenda, conclusion))
    data_client = StaticJsonLlmClient(data_responses)
    strategy_client = StaticJsonLlmClient(())
    catalogue = first_slice_tool_catalogue()
    programs = first_slice_programs()
    profiles = development_model_profiles()
    coordinator_mcp = _CoordinatorMcpClient(
        session_ref=session_ref,
        artifacts={
            manifest_ref["uri"]: manifest_ref,
            quality_ref["uri"]: quality_ref,
        },
    )
    strategy_mcp = _StrategyLoopMcpClient(manifest_ref, quality_ref)
    event_sink = RecordingObservabilityEventSink()
    event_emitter = AgentEventEmitter(
        sink=CompositeObservabilityEventSink(
            (
                ConsoleObservabilityEventSink(config=agent_console_config(os.environ)),
                event_sink,
            )
        ),
        process_instance_id="foundation-process",
    )
    coordinator = ResearchCoordinator(
        model_runner=StructuredModelRunner(
            coordinator_client,
            event_emitter=event_emitter,
        ),
        mcp_client=coordinator_mcp,
        data_agent=DataResearchAgent(
            model_runner=StructuredModelRunner(
                data_client,
                event_emitter=event_emitter,
            ),
            mcp_client=_DataLoopMcpClient(manifest_ref, quality_ref),
            tool_catalogue=catalogue,
            event_emitter=event_emitter,
        ),
        strategy_agent=StrategyEngineeringAgent(
            model_runner=StructuredModelRunner(
                strategy_client,
                event_emitter=event_emitter,
            ),
            mcp_client=strategy_mcp,
            tool_catalogue=catalogue,
            event_emitter=event_emitter,
        ),
        tool_catalogue=catalogue,
        programs=programs,
        model_profiles=profiles,
        event_emitter=event_emitter,
    )
    runtime = AgenticResearchRuntime(
        coordinator=coordinator,
        checkpointer=InMemorySaver(),
        tool_catalogue=catalogue,
        programs=programs,
        model_profiles=profiles,
        event_emitter=event_emitter,
    )

    async def _run() -> AgenticSliceResult:
        """Run the single-delegation session to its terminal decision."""
        outcome = await runtime.start(session)
        assert isinstance(outcome, AgenticSliceResult)
        return outcome

    result = anyio.run(_run)

    assert result.status == "completed"
    assert result.data_return is not None
    assert result.data_return.delegation_id == data_delegation.delegation_id
    assert result.strategy_return is None
    assert {reference.uri for reference in result.decision.cited_evidence_refs} == {
        manifest_ref["uri"],
        quality_ref["uri"],
    }
    assert result.budget_used.model_calls == 7
    assert len(coordinator_client.requests) == 2
    assert len(data_client.requests) == 5
    assert strategy_client.requests == []
    assert strategy_mcp.list_calls == 0
    assert strategy_mcp.calls == []
    assert coordinator_mcp.read_calls == 2
    assert len(coordinator_mcp.decision_payloads) == 1
    events = event_sink.events
    event_names = {event.name for event in events}
    assert {
        AgentEventName.SESSION_STARTED,
        AgentEventName.AGENDA_ACCEPTED,
        AgentEventName.SCHEDULING_COMPLETED,
        AgentEventName.DELEGATION_STARTED,
        AgentEventName.MODEL_CALL_COMPLETED,
        AgentEventName.ACTION_DOMAIN_ACCEPTED,
        AgentEventName.TOOL_EXECUTION_COMPLETED,
        AgentEventName.PHASE_CHANGED,
        AgentEventName.CHECKPOINT_SAVED,
        AgentEventName.SPECIALIST_RETURNED,
        AgentEventName.JOIN_COMPLETED,
        AgentEventName.SPECIALIST_RETURN_ACCEPTED,
        AgentEventName.EVIDENCE_REVIEW_STARTED,
        AgentEventName.EVIDENCE_REVIEW_COMPLETED,
        AgentEventName.DECISION_COMMITTED,
        AgentEventName.SESSION_COMPLETED,
    }.issubset(event_names)
    assert [event.sequence for event in events] == list(range(1, len(events) + 1))
    assert {event.correlation.session_id for event in events} == {session.session_id}
    assert {event.correlation.process_instance_id for event in events} == {
        "foundation-process"
    }
    assert {event.correlation.role for event in events} == {
        AgentRole.RESEARCH_COORDINATOR.value,
        AgentRole.DATA_RESEARCH.value,
    }
    assert not {event.level for event in events}.intersection(
        {AgentEventLevel.WARNING, AgentEventLevel.ERROR}
    )
    assert {event.correlation.model_profile_id for event in events} == {
        session.model_profile_id
    }
    assert {event.correlation.tool_catalog_id for event in events} == {
        catalogue.catalogue_id
    }
    assert {
        event.correlation.program_id
        for event in events
        if event.correlation.role == AgentRole.RESEARCH_COORDINATOR.value
    } == {programs.for_role(AgentRole.RESEARCH_COORDINATOR).program_id}
    assert {
        event.correlation.program_id
        for event in events
        if event.correlation.role == AgentRole.DATA_RESEARCH.value
    } == {programs.for_role(AgentRole.DATA_RESEARCH).program_id}

    delegation_events = [
        event for event in events if event.correlation.delegation_id is not None
    ]
    assert {event.correlation.delegation_id for event in delegation_events} == {
        data_delegation.delegation_id
    }
    assert {event.correlation.attempt_id for event in delegation_events} == {
        data_delegation.attempt_id
    }

    session_started = next(
        event for event in events if event.name is AgentEventName.SESSION_STARTED
    )
    delegation_started = next(
        event for event in events if event.name is AgentEventName.DELEGATION_STARTED
    )
    decision_committed = next(
        event for event in events if event.name is AgentEventName.DECISION_COMMITTED
    )
    session_completed = next(
        event for event in events if event.name is AgentEventName.SESSION_COMPLETED
    )
    assert session_started.fields == {
        "lifecycle_operation": "start",
        "recovered": False,
    }
    assert delegation_started.fields["task_id"] == agenda_task.task_id
    assert delegation_started.fields["join_mode"] == "hard"
    assert decision_committed.fields["receipt_ref"] == result.decision_receipt_ref.uri  # type: ignore[union-attr]
    assert session_completed.fields["status"] == "completed"
    assert (
        session_completed.fields["decision_receipt_ref"]
        == result.decision_receipt_ref.uri  # type: ignore[union-attr]
    )

    def _position(
        name: AgentEventName,
        *,
        role: AgentRole | None = None,
    ) -> int:
        """Return the first matching event position in the recorded stream."""
        return next(
            index
            for index, event in enumerate(events)
            if event.name is name
            and (role is None or event.correlation.role == role.value)
        )

    milestone_positions = [
        _position(AgentEventName.SESSION_STARTED),
        _position(AgentEventName.AGENDA_ACCEPTED),
        _position(AgentEventName.DELEGATION_STARTED),
        _position(AgentEventName.SPECIALIST_RETURNED),
        _position(AgentEventName.JOIN_COMPLETED),
        _position(AgentEventName.SPECIALIST_RETURN_ACCEPTED),
        _position(AgentEventName.EVIDENCE_REVIEW_STARTED),
        _position(AgentEventName.EVIDENCE_REVIEW_COMPLETED),
        _position(AgentEventName.DECISION_COMMITTED),
        _position(
            AgentEventName.CHECKPOINT_SAVED,
            role=AgentRole.RESEARCH_COORDINATOR,
        ),
        _position(AgentEventName.SESSION_COMPLETED),
    ]
    assert milestone_positions == sorted(milestone_positions)

    for started_name, completed_name in (
        (
            AgentEventName.MODEL_CALL_STARTED,
            AgentEventName.MODEL_CALL_COMPLETED,
        ),
        (
            AgentEventName.TOOL_EXECUTION_STARTED,
            AgentEventName.TOOL_EXECUTION_COMPLETED,
        ),
    ):
        started_events = [event for event in events if event.name is started_name]
        completed_events = [event for event in events if event.name is completed_name]
        assert {
            (event.correlation.role, event.correlation.call_id)
            for event in started_events
        } == {
            (event.correlation.role, event.correlation.call_id)
            for event in completed_events
        }
