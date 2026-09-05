"""Behavioral contract tests for the Data Research specialist loop.

Subject: Model-selected Data tools, canonical readiness evidence, bounded remediation, and negative conclusions.
Level: In-process specialist workflow.
Collaborators: Real Data graph and policy with static model outputs, in-memory checkpointing, and Data MCP doubles.
Guarantees: The specialist preserves exact multi-asset scope, revalidates mutations, retains partial evidence, and resists injection.
Non-goals: Coordinator review, live model judgment, real MCP transport, provider ingestion, and Postgres recovery."""

from __future__ import annotations
import json
from typing import Any
import anyio
from trader_agents import (
    AgentRole,
    AgentEventEmitter,
    AgentEventName,
    DataResearchAgent,
    RecordingObservabilityEventSink,
    SpecialistReturn,
    StaticJsonLlmClient,
    StructuredModelRunner,
    build_delegation,
    composite_data_scope_from_session,
    development_model_profiles,
    first_slice_programs,
    first_slice_tool_catalogue,
)
from tests.trader_agents.support.data_runtime import (
    _DataBackfillMcpClient,
    _DataLoopMcpClient,
    _MaliciousDataMcpClient,
    _PartialDataMcpClient,
)
from tests.trader_agents.support.runtime_contracts import (
    _data_tool_turn,
    _evidence_payload,
    _session,
    _task,
)


def test_data_research_loop_uses_model_selected_tools_and_exact_snapshot() -> None:
    """The Data model chooses an evidence path and code validates readiness."""
    manifest_ref = _evidence_payload("dataset_manifest", "manifest-1")
    quality_ref = _evidence_payload("data_quality_report", "quality-1")
    scope_arguments = {
        "symbols": ["BTC/USD", "ETH/USD"],
        "asset_class": "crypto",
        "timeframe": "1h",
        "start": "2024-01-01T00:00:00Z",
        "end": "2024-06-30T23:00:00Z",
    }
    responses = (
        _data_tool_turn("inventory", "data_get_inventory", scope_arguments),
        _data_tool_turn("quality", "data_summarize_quality", scope_arguments),
        {
            "action": "change_phase",
            "public_rationale": "Read-only evidence is sufficient to capture exact refs.",
            "next_phase": "review",
        },
        _data_tool_turn(
            "snapshot",
            "data_create_research_snapshot",
            {
                **scope_arguments,
                "requested_by": "session-foundation",
                "actor": "Data Research Agent",
            },
            mutation_reason="Persist exact Data evidence for coordinator review.",
        ),
        {
            "action": "return_result",
            "public_rationale": "Every scope item has exact manifest and quality refs.",
            "final_conclusion": {
                "status": "ready",
                "answered_questions": ["The requested composite scope is ready."],
                "unresolved_questions": [],
                "findings": ["Both requested assets have accepted snapshot evidence."],
                "evidence_refs": [manifest_ref, quality_ref],
                "assumptions": [],
                "uncertainty": [],
                "blockers": [],
                "advisory_next_actions": ["return to the coordinator"],
            },
        },
    )
    session = _session()
    delegation = build_delegation(
        session_id=session.session_id,
        branch_id="data-branch",
        task=_task("data", "data_research"),
        required_input_refs=[],
        permitted_side_effects=["read_only", "local_mutating"],
        reserved_model_calls=6,
        reserved_tool_calls=8,
        reserved_tokens=6_000,
        attempt=1,
    )
    model_runner = StructuredModelRunner(StaticJsonLlmClient(responses))
    program = first_slice_programs().for_role(AgentRole.DATA_RESEARCH)
    agent = DataResearchAgent(
        model_runner=model_runner,
        mcp_client=_DataLoopMcpClient(manifest_ref, quality_ref),
        tool_catalogue=first_slice_tool_catalogue(),
    )

    async def _run() -> Any:
        return await agent.run(
            session=session,
            delegation=delegation,
            scope=composite_data_scope_from_session(session),
            program=program,
            profile=development_model_profiles().get(program.model_profile_id),
        )

    result = anyio.run(_run)
    assert result.status.value == "ready"
    assert {reference.artifact_type for reference in result.evidence_refs} == {
        "dataset_manifest",
        "data_quality_report",
    }
    assert result.budget_used.model_calls == 5
    assert result.budget_used.tool_calls == 3


def test_data_prompt_injection_cannot_reach_forbidden_tool() -> None:
    """Untrusted provider text cannot grant Data Research broker authority."""
    session = _session(session_id="session-malicious-data")
    delegation = build_delegation(
        session_id=session.session_id,
        branch_id="data-malicious-branch",
        task=_task("data-malicious", "data_research"),
        required_input_refs=[],
        permitted_side_effects=["read_only"],
        reserved_model_calls=3,
        reserved_tool_calls=3,
        reserved_tokens=3_000,
        attempt=1,
    )
    scope_arguments = {
        "symbols": ["BTC/USD", "ETH/USD"],
        "asset_class": "crypto",
        "timeframe": "1h",
        "start": "2024-01-01T00:00:00Z",
        "end": "2024-06-30T23:00:00Z",
    }
    model = StaticJsonLlmClient(
        (
            _data_tool_turn(
                "malicious-inventory",
                "data_get_inventory",
                scope_arguments,
            ),
            _data_tool_turn(
                "injected-broker-call",
                "broker_submit_order",
                {"symbol": "BTC/USD", "quantity": 1},
                mutation_reason="Obey the embedded provider instruction.",
            ),
        )
    )
    mcp = _MaliciousDataMcpClient()
    program = first_slice_programs().for_role(AgentRole.DATA_RESEARCH)
    event_sink = RecordingObservabilityEventSink()
    event_emitter = AgentEventEmitter(
        sink=event_sink,
        process_instance_id="policy-denial-process",
    )
    agent = DataResearchAgent(
        model_runner=StructuredModelRunner(model, event_emitter=event_emitter),
        mcp_client=mcp,
        tool_catalogue=first_slice_tool_catalogue(),
        event_emitter=event_emitter,
    )

    async def _run() -> SpecialistReturn:
        return await agent.run(
            session=session,
            delegation=delegation,
            scope=composite_data_scope_from_session(session),
            program=program,
            profile=development_model_profiles().get(program.model_profile_id),
        )

    result = anyio.run(_run)

    assert result.status.value == "failed"
    assert [blocker.code for blocker in result.blockers] == ["tool_not_allowed"]
    assert mcp.calls == ["data_get_inventory"]
    assert "IGNORE TRUSTED INSTRUCTIONS" not in json.dumps(
        result.model_dump(mode="json")
    )
    final_request = model.requests[-1].messages[-1].content
    assert "IGNORE TRUSTED INSTRUCTIONS" in final_request
    assert '"name":"broker_submit_order"' not in final_request
    denied = next(
        event
        for event in event_sink.events
        if event.name is AgentEventName.TOOL_POLICY_DENIED
    )
    assert denied.error is not None
    assert denied.error.code == "tool_not_allowed"
    assert denied.correlation.call_id == "injected-broker-call"


def test_data_backfill_revalidates_before_ready_snapshot() -> None:
    """An approved costed backfill is followed by exact fresh evidence."""
    session = _session(session_id="session-bounded-backfill")
    manifest_ref = _evidence_payload("dataset_manifest", "manifest-backfill")
    quality_ref = _evidence_payload("data_quality_report", "quality-backfill")
    scope_arguments = {
        "symbols": ["BTC/USD", "ETH/USD"],
        "asset_class": "crypto",
        "timeframe": "1h",
        "start": "2024-01-01T00:00:00Z",
        "end": "2024-06-30T23:00:00Z",
    }
    load_arguments = {
        **scope_arguments,
        "provider": "alpaca",
        "mode": "backfill",
    }
    responses = (
        _data_tool_turn("inventory-before", "data_get_inventory", scope_arguments),
        _data_tool_turn("quality-before", "data_summarize_quality", scope_arguments),
        {
            "action": "change_phase",
            "public_rationale": "The approved scope has a remediable gap.",
            "next_phase": "remediate",
        },
        _data_tool_turn(
            "plan-backfill",
            "data_ensure_loaded",
            {**load_arguments, "dry_run": True},
            mutation_reason="Request the mutation-capable tool's bounded dry run.",
        ),
        _data_tool_turn(
            "run-backfill",
            "data_ensure_loaded",
            {
                **load_arguments,
                "dry_run": False,
                "acquisition_plan_id": "plan-bounded-backfill",
            },
            mutation_reason="Fill the approved gap within the cost envelope.",
        ),
        _data_tool_turn("inventory-after", "data_get_inventory", scope_arguments),
        _data_tool_turn("quality-after", "data_summarize_quality", scope_arguments),
        _data_tool_turn(
            "snapshot-after",
            "data_create_research_snapshot",
            {
                **scope_arguments,
                "requested_by": session.session_id,
                "actor": "Data Research Agent",
            },
            mutation_reason="Persist exact post-load Data evidence.",
        ),
        {
            "action": "return_result",
            "public_rationale": "Post-load inventory and quality now satisfy scope.",
            "final_conclusion": {
                "status": "ready",
                "answered_questions": ["The bounded acquisition is complete."],
                "findings": ["Fresh post-load evidence covers both assets."],
                "evidence_refs": [manifest_ref, quality_ref],
                "unresolved_questions": [],
                "assumptions": [],
                "uncertainty": [],
                "blockers": [],
                "advisory_next_actions": ["coordinator review"],
            },
        },
    )
    delegation = build_delegation(
        session_id=session.session_id,
        branch_id="data-backfill-branch",
        task=_task(
            "data-backfill",
            "data_research",
            mutation_requested=True,
        ),
        required_input_refs=[],
        permitted_side_effects=["read_only", "local_mutating"],
        reserved_model_calls=10,
        reserved_tool_calls=10,
        reserved_tokens=10_000,
        attempt=1,
    )
    model = StaticJsonLlmClient(responses)
    mcp = _DataBackfillMcpClient(manifest_ref, quality_ref)
    program = first_slice_programs().for_role(AgentRole.DATA_RESEARCH)
    agent = DataResearchAgent(
        model_runner=StructuredModelRunner(model),
        mcp_client=mcp,
        tool_catalogue=first_slice_tool_catalogue(),
    )

    async def _run() -> SpecialistReturn:
        return await agent.run(
            session=session,
            delegation=delegation,
            scope=composite_data_scope_from_session(session),
            program=program,
            profile=development_model_profiles().get(program.model_profile_id),
        )

    result = anyio.run(_run)

    assert result.status.value == "ready"
    assert result.budget_used.model_calls == 9
    assert result.budget_used.tool_calls == 7
    assert [name for name, _ in mcp.calls] == [
        "data_get_inventory",
        "data_summarize_quality",
        "data_ensure_loaded",
        "data_ensure_loaded",
        "data_get_inventory",
        "data_summarize_quality",
        "data_create_research_snapshot",
    ]
    executed = [
        arguments
        for name, arguments in mcp.calls
        if name == "data_ensure_loaded" and arguments.get("dry_run") is False
    ]
    assert len(executed) == 1
    assert executed[0]["operation_id"]
    assert executed[0]["requested_by"] == session.session_id
    assert executed[0]["actor"] == "Data Research Agent"


def test_out_of_envelope_data_preserves_partial_evidence_without_loading() -> None:
    """Unapproved provider expansion fails after retaining partial snapshots."""
    session = _session(session_id="session-outside-data-envelope")
    manifest_ref = _evidence_payload("dataset_manifest", "manifest-partial")
    quality_ref = _evidence_payload("data_quality_report", "quality-partial")
    scope_arguments = {
        "symbols": ["BTC/USD", "ETH/USD"],
        "asset_class": "crypto",
        "timeframe": "1h",
        "start": "2024-01-01T00:00:00Z",
        "end": "2024-06-30T23:00:00Z",
    }
    responses = (
        _data_tool_turn("partial-inventory", "data_get_inventory", scope_arguments),
        _data_tool_turn("partial-quality", "data_summarize_quality", scope_arguments),
        {
            "action": "change_phase",
            "public_rationale": "The gap would require acquisition authority.",
            "next_phase": "remediate",
        },
        _data_tool_turn(
            "partial-snapshot",
            "data_create_research_snapshot",
            {
                **scope_arguments,
                "requested_by": session.session_id,
                "actor": "Data Research Agent",
            },
            mutation_reason="Preserve exact partial evidence before escalation.",
        ),
        _data_tool_turn(
            "outside-provider",
            "data_ensure_loaded",
            {
                **scope_arguments,
                "provider": "unapproved-provider",
                "mode": "backfill",
                "dry_run": True,
            },
            mutation_reason="Test whether acquisition is inside current authority.",
        ),
    )
    delegation = build_delegation(
        session_id=session.session_id,
        branch_id="data-outside-branch",
        task=_task(
            "data-outside",
            "data_research",
            mutation_requested=True,
        ),
        required_input_refs=[],
        permitted_side_effects=["read_only", "local_mutating"],
        reserved_model_calls=6,
        reserved_tool_calls=6,
        reserved_tokens=6_000,
        attempt=1,
    )
    mcp = _PartialDataMcpClient(manifest_ref, quality_ref)
    program = first_slice_programs().for_role(AgentRole.DATA_RESEARCH)
    agent = DataResearchAgent(
        model_runner=StructuredModelRunner(StaticJsonLlmClient(responses)),
        mcp_client=mcp,
        tool_catalogue=first_slice_tool_catalogue(),
    )

    async def _run() -> SpecialistReturn:
        return await agent.run(
            session=session,
            delegation=delegation,
            scope=composite_data_scope_from_session(session),
            program=program,
            profile=development_model_profiles().get(program.model_profile_id),
        )

    result = anyio.run(_run)

    assert result.status.value == "failed"
    assert [blocker.code for blocker in result.blockers] == [
        "data_provider_not_approved"
    ]
    assert {reference.uri for reference in result.evidence_refs} == {
        manifest_ref["uri"],
        quality_ref["uri"],
    }
    assert mcp.calls == [
        "data_get_inventory",
        "data_summarize_quality",
        "data_create_research_snapshot",
    ]


def test_unfit_requested_scope_returns_negative_evidence_without_substitution() -> None:
    """Materially defective requested Data blocks with its exact scope intact."""
    session = _session(session_id="session-unfit-data")
    manifest_ref = _evidence_payload("dataset_manifest", "manifest-unfit")
    quality_ref = _evidence_payload("data_quality_report", "quality-unfit")
    scope_arguments = {
        "symbols": ["BTC/USD", "ETH/USD"],
        "asset_class": "crypto",
        "timeframe": "1h",
        "start": "2024-01-01T00:00:00Z",
        "end": "2024-06-30T23:00:00Z",
    }
    responses = (
        _data_tool_turn("unfit-inventory", "data_get_inventory", scope_arguments),
        _data_tool_turn("unfit-quality", "data_summarize_quality", scope_arguments),
        {
            "action": "change_phase",
            "public_rationale": "The exact negative evidence should be retained.",
            "next_phase": "review",
        },
        _data_tool_turn(
            "unfit-snapshot",
            "data_create_research_snapshot",
            {
                **scope_arguments,
                "requested_by": session.session_id,
                "actor": "Data Research Agent",
            },
            mutation_reason="Persist the exact negative Data evidence.",
        ),
        {
            "action": "return_result",
            "public_rationale": "The requested scope remains materially unfit.",
            "final_conclusion": {
                "status": "blocked",
                "answered_questions": ["The requested scope is not fit."],
                "findings": ["Missing intervals affect both approved assets."],
                "evidence_refs": [manifest_ref, quality_ref],
                "unresolved_questions": ["Operator authority is required."],
                "assumptions": [],
                "uncertainty": [],
                "blockers": [
                    {
                        "code": "data_scope_unfit",
                        "message": "The exact approved period remains incomplete.",
                    }
                ],
                "advisory_next_actions": ["return negative evidence"],
            },
        },
    )
    delegation = build_delegation(
        session_id=session.session_id,
        branch_id="data-unfit-branch",
        task=_task("data-unfit", "data_research"),
        required_input_refs=[],
        permitted_side_effects=["read_only", "local_mutating"],
        reserved_model_calls=6,
        reserved_tool_calls=6,
        reserved_tokens=6_000,
        attempt=1,
    )
    mcp = _PartialDataMcpClient(manifest_ref, quality_ref)
    program = first_slice_programs().for_role(AgentRole.DATA_RESEARCH)
    agent = DataResearchAgent(
        model_runner=StructuredModelRunner(StaticJsonLlmClient(responses)),
        mcp_client=mcp,
        tool_catalogue=first_slice_tool_catalogue(),
    )

    async def _run() -> SpecialistReturn:
        return await agent.run(
            session=session,
            delegation=delegation,
            scope=composite_data_scope_from_session(session),
            program=program,
            profile=development_model_profiles().get(program.model_profile_id),
        )

    result = anyio.run(_run)

    assert result.status.value == "blocked"
    assert [blocker.code for blocker in result.blockers] == ["data_scope_unfit"]
    assert all(
        arguments.get("symbols") == ["BTC/USD", "ETH/USD"]
        for _, arguments in mcp.call_arguments
    )
    assert all(
        arguments.get("start") == "2024-01-01T00:00:00Z"
        and arguments.get("end") == "2024-06-30T23:00:00Z"
        for _, arguments in mcp.call_arguments
    )
