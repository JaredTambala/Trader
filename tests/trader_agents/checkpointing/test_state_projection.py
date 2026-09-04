"""Checkpoint contracts for bounded Agent state and in-process recovery.

Subject: Public checkpoint projection, thread isolation, redaction, digest stability, and replay-safe specialist continuation.
Level: In-process checkpoint contract.
Collaborators: Real checkpoint schemas and Data graph with in-memory savers, static models, and an MCP double.
Guarantees: Stored state excludes raw content and fresh graph instances resume without repeating an accepted tool call.
Non-goals: PostgreSQL connections, coordinator decision recovery, live providers, and release qualification."""

from __future__ import annotations
import asyncio
import json
import anyio
from langgraph.checkpoint.memory import InMemorySaver
import pytest
from trader_agents import (
    AgentPhase,
    AgentRole,
    DataResearchAgent,
    SpecialistReturn,
    StaticJsonLlmClient,
    StructuredModelRunner,
    ToolObservation,
    agent_checkpoint_digest,
    build_agent_checkpoint_state,
    build_specialist_checkpoint_state,
    build_delegation,
    composite_data_scope_from_session,
    coordinator_thread_config,
    checkpoint_safe_observation,
    development_model_profiles,
    first_slice_programs,
    first_slice_tool_catalogue,
    specialist_thread_config,
    specialist_checkpoint_digest,
    validate_agent_checkpoint_state,
    validate_specialist_checkpoint_state,
)
from tests.trader_agents.support.data_runtime import _DataLoopMcpClient
from tests.trader_agents.support.runtime_contracts import (
    _data_tool_turn,
    _evidence_payload,
    _session,
    _task,
)
from tests.trader_agents.support.runtime_faults import _InterruptingJsonLlmClient


def test_checkpoint_state_is_bounded_redacted_and_thread_isolated() -> None:
    """Operational resume state excludes raw/private content by construction."""
    session = _session()
    state = build_agent_checkpoint_state(
        session_id=session.session_id,
        session_digest=session.session_digest,
        branch_id="root",
        coordinator_program_id="research-coordinator-v7",
        model_profile_id=session.model_profile_id,
        tool_catalog_id=session.tool_catalog_id,
    )
    validate_agent_checkpoint_state(state)
    assert len(agent_checkpoint_digest(state)) == 64
    coordinator = coordinator_thread_config(session.session_id)["configurable"]
    specialist = specialist_thread_config(
        session_id=session.session_id,
        delegation_id="delegation-1",
    )["configurable"]
    assert coordinator["thread_id"] != specialist["thread_id"]
    assert coordinator["thread_id"].endswith(":coordinator")
    assert ":specialist:delegation-1" in specialist["thread_id"]
    unsafe = dict(state)
    unsafe["terminal_result"] = {"api_key": "not-allowed"}
    with pytest.raises(ValueError, match="forbidden"):
        validate_agent_checkpoint_state(unsafe)


def test_specialist_checkpoint_redacts_source_and_raw_command_output() -> None:
    """Specialist recovery stores hashes and refs, never complete source text."""
    session = _session()
    delegation = build_delegation(
        session_id=session.session_id,
        branch_id="strategy-redaction",
        task=_task("strategy-redaction", "strategy_engineering"),
        required_input_refs=[],
        permitted_side_effects=["read_only", "local_mutating"],
        reserved_model_calls=4,
        reserved_tool_calls=8,
        reserved_tokens=4_000,
        attempt=1,
    )
    raw = ToolObservation(
        call_id="package-1",
        tool_name="coding_package_candidate",
        ok=True,
        command="coding_package_candidate",
        agent_owner="Strategy Engineering Agent",
        side_effect="read_only",
        summary={
            "candidate_package": {
                "package_id": "package-1",
                "source_code": "raise RuntimeError('must not persist')",
                "source_hash": "a" * 64,
                "content": "private candidate content",
                "stdout": "raw command output",
            }
        },
    )
    safe = checkpoint_safe_observation(raw)
    package = safe.summary["candidate_package"]
    assert package == {"package_id": "package-1", "source_hash": "a" * 64}

    state = build_specialist_checkpoint_state(
        session_id=session.session_id,
        session_digest=session.session_digest,
        delegation=delegation,
        role=AgentRole.STRATEGY_ENGINEERING,
        phase=AgentPhase.ADMIT.value,
        program_id="strategy-engineering-v6",
        model_profile_id=session.model_profile_id,
        tool_catalog_id=session.tool_catalog_id,
    )
    state["observations"] = [safe.model_dump(mode="json")]
    validate_specialist_checkpoint_state(state)
    assert len(specialist_checkpoint_digest(state)) == 64
    encoded = json.dumps(state)
    assert "must not persist" not in encoded
    assert "private candidate content" not in encoded
    assert "raw command output" not in encoded

    unsafe = dict(state)
    unsafe["observations"] = [raw.model_dump(mode="json")]
    with pytest.raises(ValueError, match="forbidden"):
        validate_specialist_checkpoint_state(unsafe)


def test_data_specialist_recovers_in_fresh_instance_without_repeating_tool() -> None:
    """A fresh Data agent resumes after a model interruption at a saved step."""
    session = _session()
    scope = composite_data_scope_from_session(session)
    task = _task("data-recovery", "data_research")
    delegation = build_delegation(
        session_id=session.session_id,
        branch_id="data-recovery-branch",
        task=task,
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
    manifest_ref = _evidence_payload("dataset_manifest", "recovery-manifest")
    quality_ref = _evidence_payload("data_quality_report", "recovery-quality")
    first_model = _InterruptingJsonLlmClient(
        (_data_tool_turn("inventory", "data_get_inventory", scope_arguments),)
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
            mutation_reason="Capture recovered exact Data evidence.",
        ),
        {
            "action": "return_result",
            "public_rationale": "Recovered evidence covers the exact scope.",
            "final_conclusion": {
                "status": "ready",
                "answered_questions": ["The requested Data is ready."],
                "findings": ["Recovery retained the completed inventory step."],
                "evidence_refs": [manifest_ref, quality_ref],
                "unresolved_questions": [],
                "assumptions": [],
                "uncertainty": [],
                "blockers": [],
                "advisory_next_actions": ["coordinator review"],
            },
        },
    )
    mcp = _DataLoopMcpClient(manifest_ref, quality_ref)
    catalogue = first_slice_tool_catalogue()
    program = first_slice_programs().for_role(AgentRole.DATA_RESEARCH)
    profile = development_model_profiles().get(program.model_profile_id)
    saver = InMemorySaver()

    async def _run() -> SpecialistReturn:
        interrupted_agent = DataResearchAgent(
            model_runner=StructuredModelRunner(first_model),
            mcp_client=mcp,
            tool_catalogue=catalogue,
        )
        with pytest.raises(asyncio.CancelledError):
            await interrupted_agent.run(
                session=session,
                delegation=delegation,
                scope=scope,
                program=program,
                profile=profile,
                checkpointer=saver,
            )
        recovered_agent = DataResearchAgent(
            model_runner=StructuredModelRunner(StaticJsonLlmClient(remaining)),
            mcp_client=mcp,
            tool_catalogue=catalogue,
        )
        return await recovered_agent.run(
            session=session,
            delegation=delegation,
            scope=scope,
            program=program,
            profile=profile,
            checkpointer=saver,
        )

    result = anyio.run(_run)
    assert result.status.value == "ready"
    assert mcp.calls.count("data_get_inventory") == 1
    assert mcp.calls == [
        "data_get_inventory",
        "data_summarize_quality",
        "data_create_research_snapshot",
    ]
