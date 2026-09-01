"""Contract, policy, model, MCP, and checkpoint tests for agent runtime."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from hashlib import sha256
from typing import Any

import anyio
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command
import pytest
from pydantic import ValidationError

from trader_agents import (
    AgentPhase,
    AgentRole,
    AgenticSliceResult,
    AgendaTaskProposal,
    BudgetLedger,
    CompositeDataScope,
    CanonicalEvidenceRef,
    CoordinatorAgenda,
    DataAgentTurn,
    DataInputRole,
    DataResearchAgent,
    DataScopeItem,
    LlmTokenUsage,
    McpToolDescription,
    ParameterContract,
    PolicyContext,
    PolicyViolation,
    RecordingTraceSink,
    ResearchCoordinator,
    RoleScopedMcpRuntime,
    StaticJsonLlmClient,
    StrategyEngineeringAgent,
    StructuredModelRunner,
    ToolCallProposal,
    ToolPolicy,
    TraceCorrelation,
    agent_checkpoint_digest,
    build_agent_checkpoint_state,
    build_delegation,
    composite_data_scope_from_session,
    compute_ready_set,
    coordinator_thread_config,
    development_model_profiles,
    first_slice_programs,
    first_slice_tool_catalogue,
    specialist_thread_config,
    strategy_build_contract_from_session,
    validate_agent_checkpoint_state,
    validate_runtime_pins,
)
from trader_research.foundation import stable_research_id
from trader_research.governance import AgentBudget, ResearchSession


def test_agenda_rejects_cycles_and_unknown_fields() -> None:
    """The model cannot smuggle fields or submit an unschedulable DAG."""
    with pytest.raises(ValidationError, match="cycle"):
        CoordinatorAgenda(
            objective_summary="Inspect Data and implementation evidence.",
            tasks=[
                _task("data", "data_research", dependencies=["strategy"]),
                _task(
                    "strategy",
                    "strategy_engineering",
                    dependencies=["data"],
                ),
            ],
        )
    with pytest.raises(ValidationError, match="Extra inputs"):
        DataAgentTurn.model_validate(
            {
                "action": "change_phase",
                "public_rationale": "Coverage gap requires approved remediation.",
                "next_phase": "remediate",
                "hidden_reasoning": "do not persist",
            }
        )


def test_parameter_contract_enforces_declared_type_and_bounds() -> None:
    """Typed build inputs reject Python's bool-as-int ambiguity."""
    with pytest.raises(ValidationError, match="integer parameter"):
        ParameterContract(
            name="window",
            value_type="integer",
            default=True,
            minimum=1,
            maximum=100,
            tunable=True,
            semantics="Lookback bars.",
        )
    with pytest.raises(ValidationError, match="above maximum"):
        ParameterContract(
            name="window",
            value_type="integer",
            default=101,
            minimum=1,
            maximum=100,
            tunable=True,
            semantics="Lookback bars.",
        )


def test_session_inputs_and_runtime_pins_normalize_exact_contracts() -> None:
    """A session enters runtime only through strict Data and build contracts."""
    session = _session()
    scope = composite_data_scope_from_session(session)
    contract = strategy_build_contract_from_session(
        session,
        branch_id="strategy-branch",
    )
    validate_runtime_pins(
        session,
        model_profiles=development_model_profiles(),
        agent_programs=first_slice_programs(),
        tool_catalogue=first_slice_tool_catalogue(),
    )
    assert scope.session_id == session.session_id
    assert {symbol for item in scope.items for symbol in item.symbols} == {
        "BTC/USD",
        "ETH/USD",
    }
    assert contract.provenance == "operator_specified"
    assert contract.branch_id == "strategy-branch"


def test_role_catalogue_and_policy_fail_closed() -> None:
    """Data cannot see broker tools or widen its approved composite scope."""
    session = _session()
    catalogue = first_slice_tool_catalogue()
    visible = catalogue.available(
        role=AgentRole.DATA_RESEARCH,
        phase=AgentPhase.INVESTIGATE,
        approval_policy=session.approval_policy,
    )
    assert "data_get_inventory" in {item.name for item in visible}
    assert all("broker" not in item.name for item in visible)
    delegation = build_delegation(
        session_id=session.session_id,
        branch_id="data-branch",
        task=_task("data", "data_research"),
        required_input_refs=[],
        permitted_side_effects=["read_only"],
        reserved_model_calls=4,
        reserved_tool_calls=8,
        reserved_tokens=4_000,
        attempt=1,
    )
    context = PolicyContext(
        session=session,
        role=AgentRole.DATA_RESEARCH,
        phase=AgentPhase.INVESTIGATE,
        program_id="data-research-v1",
        tool_catalogue=catalogue,
        usage=BudgetLedger(session.budget).usage,
        runtime_state={},
        loop_fingerprints={},
        delegation=delegation,
        data_scope=composite_data_scope_from_session(session),
    )
    proposal = ToolCallProposal(
        call_id="outside",
        tool_name="data_get_inventory",
        arguments={
            "symbols": ["SOL/USD"],
            "asset_class": "crypto",
            "timeframe": "1h",
            "start": "2024-01-01T00:00:00Z",
            "end": "2024-06-30T23:00:00Z",
        },
        purpose="Inspect an unapproved symbol.",
        expected_evidence=["inventory"],
    )
    with pytest.raises(PolicyViolation) as raised:
        ToolPolicy().authorize(proposal, context)
    assert raised.value.code == "data_scope_expansion"


def test_scheduler_parallelizes_ready_work_and_honors_hard_joins() -> None:
    """Independent work runs together while dependent/conflicting work waits."""
    agenda = CoordinatorAgenda(
        objective_summary="Prepare exact Data and implementation evidence.",
        tasks=[
            _task("data", "data_research"),
            _task("strategy", "strategy_engineering"),
            _task(
                "data-remediation",
                "data_research",
                dependencies=["data"],
                mutation_requested=True,
            ),
        ],
    )
    first = compute_ready_set(
        agenda,
        completed_task_ids=[],
        mutation_keys_by_task={"data-remediation": ["dataset:prices"]},
        budget=_budget(),
        usage=BudgetLedger(_budget()).usage,
    )
    assert [item.task.task_id for item in first] == ["data", "strategy"]
    second = compute_ready_set(
        agenda,
        completed_task_ids=["data", "strategy"],
        active_mutation_keys=["dataset:prices"],
        mutation_keys_by_task={"data-remediation": ["dataset:prices"]},
        budget=_budget(),
        usage=BudgetLedger(_budget()).usage,
    )
    assert second == ()


def test_structured_model_repairs_once_and_records_redacted_spans() -> None:
    """Malformed public JSON receives one bounded schema-only repair."""
    valid = {
        "action": "change_phase",
        "public_rationale": "Inventory evidence shows an approved loading gap.",
        "next_phase": "remediate",
    }
    client = StaticJsonLlmClient(
        responses=({}, valid),
        usages=(LlmTokenUsage(10, 4), LlmTokenUsage(12, 6)),
    )
    traces = RecordingTraceSink()
    runner = StructuredModelRunner(client=client, trace_sink=traces)
    program = first_slice_programs().for_role(AgentRole.DATA_RESEARCH)
    profile = development_model_profiles().get(program.model_profile_id)
    ledger = BudgetLedger(_budget())
    async def _run() -> Any:
        return await runner.invoke(
            program=program,
            profile=profile,
            output_type=DataAgentTurn,
            instruction="Choose the next evidence-producing action.",
            public_context={"observations": []},
            ledger=ledger,
            correlation=_correlation(program.program_id),
        )

    result = anyio.run(_run)
    assert result.output.action == "change_phase"
    assert result.schema_repairs == 1
    assert ledger.usage.model_calls == 2
    assert len(client.requests) == 2
    assert {span["status"] for span in traces.spans} == {"completed"}
    assert all("prompt" not in str(span["attributes"]) for span in traces.spans)


def test_role_scoped_mcp_runtime_validates_transport_envelope() -> None:
    """Only the code-owned schema, owner, and side effect reach the model."""
    session = _session()
    scope = composite_data_scope_from_session(session)
    delegation = build_delegation(
        session_id=session.session_id,
        branch_id="data-branch",
        task=_task("data", "data_research"),
        required_input_refs=[],
        permitted_side_effects=["read_only"],
        reserved_model_calls=4,
        reserved_tool_calls=8,
        reserved_tokens=4_000,
        attempt=1,
    )
    ledger = BudgetLedger(session.budget)
    client = _FakeMcpClient()
    runtime = RoleScopedMcpRuntime(
        client=client,
        catalogue=first_slice_tool_catalogue(),
        ledger=ledger,
    )
    context = PolicyContext(
        session=session,
        role=AgentRole.DATA_RESEARCH,
        phase=AgentPhase.INVESTIGATE,
        program_id="data-research-v1",
        tool_catalogue=runtime.catalogue,
        usage=ledger.usage,
        runtime_state={},
        loop_fingerprints={},
        delegation=delegation,
        data_scope=scope,
    )
    proposal = ToolCallProposal(
        call_id="inventory-1",
        tool_name="data_get_inventory",
        arguments={
            "symbols": ["BTC/USD", "ETH/USD"],
            "asset_class": "crypto",
            "timeframe": "1h",
            "start": "2024-01-01T00:00:00Z",
            "end": "2024-06-30T23:00:00Z",
        },
        purpose="Inspect exact requested coverage.",
        expected_evidence=["coverage gaps"],
    )
    async def _run() -> Any:
        return await runtime.execute(
            proposal,
            context=context,
            correlation=_correlation("data-research-v1"),
        )

    result = anyio.run(_run)
    assert result.observation.ok is True
    assert result.observation.summary["coverage"] == "complete"
    assert ledger.usage.tool_calls == 1


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


def test_strategy_loop_requires_catalogue_comparison_for_exact_reuse() -> None:
    """The Strategy model may reuse only an exact independently admitted match."""
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
    session = _session()
    contract = strategy_build_contract_from_session(
        session,
        branch_id="strategy-branch",
    )
    responses = (
        _strategy_tool_turn(
            "search",
            "research_search_implementations",
            {
                "query": "cross asset momentum",
                "implementation_kinds": ["strategy"],
                "include_unadmitted": False,
                "limit": 10,
            },
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
            "public_rationale": "The exact admitted version matches every contract field.",
            "build_decision": "reuse",
        },
        {
            "action": "return_result",
            "public_rationale": "Independent admission and comparison support reuse.",
            "final_conclusion": {
                "status": "ready",
                "answered_questions": ["An exact admitted implementation is reusable."],
                "unresolved_questions": [],
                "findings": ["Field comparison found no differences or unknowns."],
                "evidence_refs": [implementation_ref, validation_ref],
                "assumptions": [],
                "uncertainty": [],
                "blockers": [],
                "advisory_next_actions": ["return to the coordinator"],
            },
        },
    )
    delegation = build_delegation(
        session_id=session.session_id,
        branch_id="strategy-branch",
        task=_task("strategy", "strategy_engineering"),
        required_input_refs=[],
        permitted_side_effects=["read_only"],
        reserved_model_calls=6,
        reserved_tool_calls=6,
        reserved_tokens=6_000,
        attempt=1,
    )
    program = first_slice_programs().for_role(AgentRole.STRATEGY_ENGINEERING)
    agent = StrategyEngineeringAgent(
        model_runner=StructuredModelRunner(StaticJsonLlmClient(responses)),
        mcp_client=_StrategyLoopMcpClient(
            implementation_ref,
            validation_ref,
        ),
        tool_catalogue=first_slice_tool_catalogue(),
    )

    async def _run() -> Any:
        return await agent.run(
            session=session,
            delegation=delegation,
            build_contract=contract,
            program=program,
            profile=development_model_profiles().get(program.model_profile_id),
        )

    result = anyio.run(_run)
    assert result.status.value == "ready"
    assert result.budget_used.model_calls == 5
    assert result.budget_used.tool_calls == 3
    assert {reference.artifact_type for reference in result.evidence_refs} == {
        "implementation_version",
        "implementation_validation_report",
    }


def test_strategy_loop_authors_checks_admits_and_cleans_workspace() -> None:
    """New code stays in MCP workspace and admission remains independent."""
    session = _session()
    contract = strategy_build_contract_from_session(
        session,
        branch_id="strategy-branch",
    )
    delegation = build_delegation(
        session_id=session.session_id,
        branch_id="strategy-branch",
        task=_task("strategy", "strategy_engineering"),
        required_input_refs=[],
        permitted_side_effects=["read_only", "local_mutating"],
        reserved_model_calls=12,
        reserved_tool_calls=12,
        reserved_tokens=12_000,
        attempt=1,
    )
    candidate_attempt = stable_research_id(
        "candidate_attempt",
        {
            "delegation_id": delegation.delegation_id,
            "specialist_attempt_id": delegation.attempt_id,
            "repair_count": 0,
        },
    )
    workspace_id = "workspace-author-1"
    source = (
        '"""Candidate strategy produced from the approved build contract."""\n\n'
        "def build_strategy():\n"
        "    \"\"\"Return a deterministic candidate marker.\"\"\"\n"
        "    return {'name': 'CrossAssetMomentum'}\n"
    )
    implementation_ref = _evidence_payload(
        "implementation_version",
        "implementation-authored-1",
        domain_owner="Experiments",
    )
    validation_ref = _evidence_payload(
        "implementation_validation_report",
        "validation-authored-1",
        domain_owner="Experiments",
    )
    responses = (
        _strategy_tool_turn(
            "search",
            "research_search_implementations",
            {"query": "cross asset momentum", "implementation_kinds": ["strategy"]},
        ),
        {
            "action": "choose_build",
            "public_rationale": "No catalogue candidate matches the approved contract.",
            "build_decision": "author",
        },
        _strategy_tool_turn(
            "create",
            "coding_create_workspace",
            {
                "attempt_id": candidate_attempt,
                "build_contract_id": contract.contract_id,
            },
            mutation_reason="Create the isolated candidate attempt workspace.",
        ),
        _strategy_tool_turn(
            "write-implementation",
            "coding_write_candidate_file",
            {
                "workspace_id": workspace_id,
                "relative_path": "implementation.py",
                "content": source,
            },
            mutation_reason="Write the contract-derived candidate source.",
        ),
        _strategy_tool_turn(
            "write-tests",
            "coding_write_candidate_file",
            {
                "workspace_id": workspace_id,
                "relative_path": "test_implementation.py",
                "content": "def test_candidate_exists():\n    assert True\n",
            },
            mutation_reason="Write bounded candidate conformance tests.",
        ),
        _strategy_tool_turn(
            "dependencies",
            "coding_resolve_dependencies",
            {"workspace_id": workspace_id, "dependencies": []},
        ),
        _strategy_tool_turn(
            "check",
            "coding_run_check",
            {"workspace_id": workspace_id, "check_name": "pytest"},
            mutation_reason="Run the allowlisted isolated candidate checks.",
        ),
        _strategy_tool_turn(
            "package",
            "coding_package_candidate",
            {"workspace_id": workspace_id, "implementation_path": "implementation.py"},
        ),
        _strategy_tool_turn(
            "register",
            "research_register_strategy_implementation",
            {
                "name": contract.name,
                "version": "0.1.0",
                "source_code": source,
                "factory_name": "build_strategy",
                "dependencies": [],
                "authoring_origin": "agent_authored",
                "metadata": {"candidate_package_id": "package-author-1"},
            },
            mutation_reason="Register the exact inert candidate package.",
        ),
        _strategy_tool_turn(
            "validate",
            "research_validate_strategy_implementation",
            {
                "implementation_version_uri": implementation_ref["uri"],
                "requested_by": session.session_id,
                "actor": "Strategy Engineering Agent",
            },
            mutation_reason="Request independent deterministic admission.",
        ),
        {
            "action": "return_result",
            "public_rationale": "The exact candidate passed independent admission.",
            "final_conclusion": {
                "status": "ready",
                "answered_questions": ["A new candidate was admitted."],
                "findings": ["Isolated checks and independent admission passed."],
                "evidence_refs": [implementation_ref, validation_ref],
                "unresolved_questions": [],
                "assumptions": [],
                "uncertainty": [],
                "blockers": [],
                "advisory_next_actions": ["coordinator review"],
            },
        },
    )
    mcp = _StrategyBuildMcpClient(
        workspace_id=workspace_id,
        source=source,
        implementation_ref=implementation_ref,
        validation_ref=validation_ref,
    )
    program = first_slice_programs().for_role(AgentRole.STRATEGY_ENGINEERING)
    agent = StrategyEngineeringAgent(
        model_runner=StructuredModelRunner(StaticJsonLlmClient(responses)),
        mcp_client=mcp,
        tool_catalogue=first_slice_tool_catalogue(),
    )

    async def _run() -> Any:
        return await agent.run(
            session=session,
            delegation=delegation,
            build_contract=contract,
            program=program,
            profile=development_model_profiles().get(program.model_profile_id),
        )

    result = anyio.run(_run)
    assert result.status.value == "ready"
    assert result.budget_used.model_calls == 11
    assert result.budget_used.tool_calls == 10
    assert mcp.destroyed is True


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
            _task("data", "data_research").model_dump(mode="json"),
            _task("strategy", "strategy_engineering").model_dump(mode="json"),
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
        task=_task("data", "data_research"),
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
        task=_task("strategy", "strategy_engineering"),
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
        model_runner=StructuredModelRunner(coordinator_client),
        mcp_client=coordinator_mcp,
        data_agent=DataResearchAgent(
            model_runner=StructuredModelRunner(
                StaticJsonLlmClient(data_responses)
            ),
            mcp_client=_DataLoopMcpClient(manifest_ref, quality_ref),
            tool_catalogue=catalogue,
        ),
        strategy_agent=StrategyEngineeringAgent(
            model_runner=StructuredModelRunner(
                StaticJsonLlmClient(strategy_responses)
            ),
            mcp_client=_StrategyLoopMcpClient(
                implementation_ref,
                validation_ref,
            ),
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
        coordinator_program_id="research-coordinator-v1",
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
        coordinator_program_id="research-coordinator-v1",
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


def test_checkpoint_state_is_bounded_redacted_and_thread_isolated() -> None:
    """Operational resume state excludes raw/private content by construction."""
    session = _session()
    state = build_agent_checkpoint_state(
        session_id=session.session_id,
        session_digest=session.session_digest,
        branch_id="root",
        coordinator_program_id="research-coordinator-v1",
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
    assert coordinator["thread_id"] == specialist["thread_id"]
    assert coordinator["checkpoint_ns"] != specialist["checkpoint_ns"]
    unsafe = dict(state)
    unsafe["terminal_result"] = {"api_key": "not-allowed"}
    with pytest.raises(ValueError, match="forbidden"):
        validate_agent_checkpoint_state(unsafe)


@dataclass
class _FakeMcpClient:
    """Small MCP transport fake with one Data inventory operation."""

    async def list_tools(self) -> Sequence[McpToolDescription]:
        """Return the exact test input schema."""
        return (
            McpToolDescription(
                name="data_get_inventory",
                description="Inspect data inventory.",
                input_schema={
                    "type": "object",
                    "required": [
                        "symbols",
                        "asset_class",
                        "timeframe",
                        "start",
                        "end",
                    ],
                    "properties": {
                        "symbols": {"type": "array"},
                        "asset_class": {"type": "string"},
                        "timeframe": {"type": "string"},
                        "start": {"type": "string"},
                        "end": {"type": "string"},
                    },
                    "additionalProperties": False,
                },
            ),
        )

    async def call_tool(
        self,
        tool_name: str,
        arguments: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        """Return a valid bounded MCP application envelope."""
        assert tool_name == "data_get_inventory"
        assert arguments["symbols"] == ["BTC/USD", "ETH/USD"]
        return {
            "structuredContent": {
                "ok": True,
                "command": tool_name,
                "agent_owner": "Data Agent",
                "side_effect": "read_only",
                "data": {"coverage": "complete"},
                "artifacts": {},
                "warnings": [],
                "errors": [],
            },
            "isError": False,
        }


@dataclass
class _DataLoopMcpClient:
    """MCP fake covering the complete ready Data path."""

    manifest_ref: Mapping[str, Any]
    quality_ref: Mapping[str, Any]

    async def list_tools(self) -> Sequence[McpToolDescription]:
        """Expose every code-owned Data capability with permissive test schemas."""
        catalogue = first_slice_tool_catalogue()
        names = {
            definition.name
            for phase in AgentPhase
            for definition in catalogue.available(
                role=AgentRole.DATA_RESEARCH,
                phase=phase,
                approval_policy={
                    "data_loading": "approved",
                    "coding_workspace": "approved",
                },
            )
        }
        return tuple(
            McpToolDescription(
                name=name,
                description=f"Test schema for {name}.",
                input_schema={"type": "object", "additionalProperties": True},
            )
            for name in sorted(names)
        )

    async def call_tool(
        self,
        tool_name: str,
        arguments: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        """Return read-only observations or exact snapshot refs."""
        side_effect = (
            "local_mutating"
            if tool_name == "data_create_research_snapshot"
            else "read_only"
        )
        artifacts: Mapping[str, Any] = {}
        if tool_name == "data_create_research_snapshot":
            artifacts = {
                "dataset_manifest": self.manifest_ref,
                "data_quality_report": self.quality_ref,
            }
        return {
            "structuredContent": {
                "ok": True,
                "command": tool_name,
                "agent_owner": "Data Agent",
                "side_effect": side_effect,
                "data": {"complete": True, "arguments": dict(arguments)},
                "artifacts": artifacts,
                "warnings": [],
                "errors": [],
            },
            "isError": False,
        }


@dataclass
class _StrategyLoopMcpClient:
    """MCP fake covering exact admitted implementation reuse."""

    implementation_ref: Mapping[str, Any]
    validation_ref: Mapping[str, Any]

    async def list_tools(self) -> Sequence[McpToolDescription]:
        """Expose every Strategy capability with permissive test schemas."""
        catalogue = first_slice_tool_catalogue()
        names = {
            definition.name
            for phase in AgentPhase
            for definition in catalogue.available(
                role=AgentRole.STRATEGY_ENGINEERING,
                phase=phase,
                approval_policy={
                    "data_loading": "approved",
                    "coding_workspace": "approved",
                },
            )
        }
        return tuple(
            McpToolDescription(
                name=name,
                description=f"Test schema for {name}.",
                input_schema={"type": "object", "additionalProperties": True},
            )
            for name in sorted(names)
        )

    async def call_tool(
        self,
        tool_name: str,
        arguments: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        """Return catalogue results and exact admitted refs."""
        data: dict[str, Any]
        artifacts: Mapping[str, Any] = {}
        if tool_name == "research_search_implementations":
            data = {"result_count": 1, "implementations": [{"trust_tier": "admitted"}]}
        elif tool_name == "research_get_implementation":
            data = {"implementation": {"direct_reuse_eligible": True}}
            artifacts = {
                "implementation_version": self.implementation_ref,
                "implementation_validation_report": self.validation_ref,
            }
        elif tool_name == "research_compare_implementation":
            data = {"direct_reuse_eligible": True, "fields": []}
            artifacts = {
                "implementation_version": self.implementation_ref,
                "implementation_validation_report": self.validation_ref,
            }
        else:
            raise AssertionError(f"unexpected Strategy tool: {tool_name}")
        return {
            "structuredContent": {
                "ok": True,
                "command": tool_name,
                "agent_owner": "Strategy Engineering Agent",
                "side_effect": "read_only",
                "data": data,
                "artifacts": artifacts,
                "warnings": [],
                "errors": [],
            },
            "isError": False,
        }


@dataclass
class _CoordinatorMcpClient:
    """Coordinator MCP fake with canonical reads and decision receipts."""

    session_ref: Mapping[str, Any]
    artifacts: Mapping[str, Mapping[str, Any]]
    read_calls: int = 0

    async def list_tools(self) -> Sequence[McpToolDescription]:
        """Expose every coordinator capability with permissive test schemas."""
        catalogue = first_slice_tool_catalogue()
        names = {
            definition.name
            for phase in AgentPhase
            for definition in catalogue.available(
                role=AgentRole.RESEARCH_COORDINATOR,
                phase=phase,
                approval_policy={},
            )
        }
        return tuple(
            McpToolDescription(
                name=name,
                description=f"Test schema for {name}.",
                input_schema={"type": "object", "additionalProperties": True},
            )
            for name in sorted(names)
        )

    async def call_tool(
        self,
        tool_name: str,
        arguments: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        """Persist session/receipt identities and verify exact test refs."""
        side_effect = "read_only"
        data: dict[str, Any]
        artifacts: Mapping[str, Any]
        if tool_name == "research_create_agent_session":
            side_effect = "local_mutating"
            data = {"research_session": arguments["session"]}
            artifacts = {"research_session": self.session_ref}
        elif tool_name == "research_read_artifact":
            self.read_calls += 1
            reference = self.artifacts[str(arguments["artifact_ref"])]
            data = {
                "record": {
                    "artifact_type": reference["artifact_type"],
                    "artifact_id": reference["artifact_id"],
                    "domain_owner": reference["domain_owner"],
                    "producer_tool": "test_fixture",
                    "status": "passed",
                    "payload_hash": "a" * 64,
                    "source_hash": None,
                }
            }
            artifacts = {"artifact": reference}
        elif tool_name == "research_record_agent_decision":
            side_effect = "local_mutating"
            receipt = arguments["receipt"]
            receipt_id = str(receipt["receipt_id"])
            reference = _evidence_payload(
                "agent_decision_receipt",
                receipt_id,
                domain_owner="Orchestration",
            )
            data = {"agent_decision_receipt": receipt}
            artifacts = {"agent_decision_receipt": reference}
        else:
            raise AssertionError(f"unexpected coordinator tool: {tool_name}")
        return {
            "structuredContent": {
                "ok": True,
                "command": tool_name,
                "agent_owner": "Research Coordinator",
                "side_effect": side_effect,
                "data": data,
                "artifacts": artifacts,
                "warnings": [],
                "errors": [],
            },
            "isError": False,
        }


@dataclass
class _StrategyBuildMcpClient:
    """MCP fake covering isolated authorship through terminal cleanup."""

    workspace_id: str
    source: str
    implementation_ref: Mapping[str, Any]
    validation_ref: Mapping[str, Any]
    destroyed: bool = False

    async def list_tools(self) -> Sequence[McpToolDescription]:
        """Expose every Strategy capability with permissive test schemas."""
        catalogue = first_slice_tool_catalogue()
        names = {
            definition.name
            for phase in AgentPhase
            for definition in catalogue.available(
                role=AgentRole.STRATEGY_ENGINEERING,
                phase=phase,
                approval_policy={"coding_workspace": "approved"},
            )
        }
        return tuple(
            McpToolDescription(
                name=name,
                description=f"Test schema for {name}.",
                input_schema={"type": "object", "additionalProperties": True},
            )
            for name in sorted(names)
        )

    async def call_tool(
        self,
        tool_name: str,
        arguments: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        """Return exact lifecycle evidence for each proposed operation."""
        artifacts: Mapping[str, Any] = {}
        side_effect = "local_mutating"
        if tool_name == "research_search_implementations":
            side_effect = "read_only"
            data: dict[str, Any] = {"result_count": 0, "implementations": []}
        elif tool_name == "coding_create_workspace":
            data = {"workspace": {"workspace_id": self.workspace_id}}
        elif tool_name == "coding_write_candidate_file":
            data = {"workspace_id": self.workspace_id, "content_sha256": "b" * 64}
        elif tool_name == "coding_resolve_dependencies":
            side_effect = "read_only"
            data = {"workspace_id": self.workspace_id, "dependencies": []}
        elif tool_name == "coding_run_check":
            data = {"check": {"check_name": "pytest", "status": "passed"}}
        elif tool_name == "coding_package_candidate":
            side_effect = "read_only"
            data = {
                "candidate_package": {
                    "package_id": "package-author-1",
                    "source_hash": sha256(self.source.encode("utf-8")).hexdigest(),
                    "source_code": self.source,
                }
            }
        elif tool_name == "research_register_strategy_implementation":
            data = {"implementation_version": {"status": "registered"}}
            artifacts = {"implementation_version": self.implementation_ref}
        elif tool_name == "research_validate_strategy_implementation":
            data = {"implementation_validation_report": {"status": "passed"}}
            artifacts = {
                "implementation_validation_report": self.validation_ref
            }
        elif tool_name == "coding_destroy_workspace":
            self.destroyed = True
            data = {"workspace_id": self.workspace_id, "status": "destroyed"}
        else:
            raise AssertionError(f"unexpected Strategy build tool: {tool_name}")
        return {
            "structuredContent": {
                "ok": True,
                "command": tool_name,
                "agent_owner": "Strategy Engineering Agent",
                "side_effect": side_effect,
                "data": data,
                "artifacts": artifacts,
                "warnings": [],
                "errors": [],
            },
            "isError": False,
        }


def _session() -> ResearchSession:
    """Build one complete first-slice session fixture."""
    catalogue = first_slice_tool_catalogue()
    programs = first_slice_programs()
    return ResearchSession(
        session_id="session-foundation",
        objective="Prepare a multi-asset momentum candidate.",
        success_definition="Return exact Data and admission evidence.",
        operator_id="operator-test",
        approval_policy={
            "data_loading": "preapproved_within_scope",
            "coding_workspace": "approved",
        },
        scope_envelope={
            "data_scope": CompositeDataScope(
                scope_id="scope-foundation",
                session_id="session-foundation",
                items=[
                    DataScopeItem(
                        item_id="prices",
                        data_role="primary_prices",
                        symbols=["BTC/USD", "ETH/USD"],
                        asset_class="crypto",
                        data_type="bars",
                        fields=["open", "high", "low", "close", "volume"],
                        timeframe="1h",
                        start="2024-01-01T00:00:00Z",
                        end="2024-06-30T23:00:00Z",
                        permitted_providers=["alpaca"],
                        quality_requirements=["complete coverage"],
                        requirement_sources=["operator brief"],
                    )
                ],
                loading_approved=True,
                max_loading_cost=10.0,
            ).model_dump(mode="json")
        },
        implementation_specification={
            "approval_id": "approval-1",
            "implementation_kind": "strategy",
            "name": "CrossAssetMomentum",
            "runtime_interface": "Strategy",
            "portfolio_mode": "multi_asset",
            "decision_rules": ["Rank trailing returns and hold the leader."],
            "state_transitions": ["Rebalance at each completed hourly bar."],
            "timing": "Use only completed hourly bars.",
            "warmup_bars": 25,
            "missing_value_policy": "Do not emit signals until all inputs exist.",
            "failure_behavior": "Fail closed on stale or missing prices.",
            "input_roles": [
                DataInputRole(
                    role="primary_prices",
                    fields=["close"],
                    timeframe="1h",
                    units="USD",
                    timing="completed bars",
                ).model_dump(mode="json")
            ],
            "parameters": [
                ParameterContract(
                    name="lookback",
                    value_type="integer",
                    default=24,
                    minimum=2,
                    maximum=200,
                    tunable=True,
                    semantics="Trailing completed bars used for return.",
                ).model_dump(mode="json")
            ],
            "responsibilities": ["Generate target allocations."],
            "permitted_dependencies": [],
            "required_fixtures": ["two-asset hourly bars"],
            "trader_interface_version": "1",
            "python_version": "3.12",
            "code_quality_ref": "docs/python_code_quality.md",
            "repository_revision": "2711493",
            "max_repairs": 1,
        },
        implementation_ref=None,
        python_quality_guide="docs/python_code_quality.md",
        model_profile_id="ollama-qwen35-9b-json-v1",
        agent_program_ids=tuple(
            programs.for_role(role).program_id for role in AgentRole
        ),
        tool_catalog_id=catalogue.catalogue_id,
        budget=_budget(),
    )


def _budget() -> AgentBudget:
    """Return bounded test-session resource ceilings."""
    return AgentBudget(
        max_model_calls=12,
        max_tool_calls=24,
        max_tokens=12_000,
        max_duration_seconds=600,
        max_mutations=8,
        max_revisions=2,
        concurrency_limit=2,
    )


def _task(
    task_id: str,
    role: str,
    *,
    dependencies: list[str] | None = None,
    mutation_requested: bool = False,
) -> AgendaTaskProposal:
    """Build one visible agenda task fixture."""
    return AgendaTaskProposal(
        task_id=task_id,
        role=role,  # type: ignore[arg-type]
        question="Return the required canonical evidence.",
        required_evidence=["exact canonical refs"],
        dependencies=dependencies or [],
        expected_information_gain="Resolve readiness for the coordinator.",
        mutation_requested=mutation_requested,
    )


def _correlation(program_id: str) -> TraceCorrelation:
    """Build stable test trace identities."""
    return TraceCorrelation(
        session_id="session-foundation",
        branch_id="data-branch",
        program_id=program_id,
        model_profile_id="ollama-qwen35-9b-json-v1",
        tool_catalog_id=first_slice_tool_catalogue().catalogue_id,
    )


def _data_tool_turn(
    call_id: str,
    tool_name: str,
    arguments: Mapping[str, Any],
    *,
    mutation_reason: str | None = None,
) -> dict[str, Any]:
    """Build one strict Data call-tool model response."""
    return {
        "action": "call_tool",
        "public_rationale": f"Use {tool_name} to gather required evidence.",
        "tool_call": {
            "call_id": call_id,
            "tool_name": tool_name,
            "arguments": dict(arguments),
            "purpose": "Gather exact evidence for the approved Data scope.",
            "expected_evidence": ["bounded Data evidence"],
            "mutation_reason": mutation_reason,
        },
    }


def _strategy_tool_turn(
    call_id: str,
    tool_name: str,
    arguments: Mapping[str, Any],
    *,
    mutation_reason: str | None = None,
) -> dict[str, Any]:
    """Build one strict Strategy call-tool model response."""
    return {
        "action": "call_tool",
        "public_rationale": f"Use {tool_name} for catalogue/build evidence.",
        "tool_call": {
            "call_id": call_id,
            "tool_name": tool_name,
            "arguments": dict(arguments),
            "purpose": "Gather exact implementation evidence.",
            "expected_evidence": ["bounded implementation evidence"],
            "mutation_reason": mutation_reason,
        },
    }


def _evidence_payload(
    artifact_type: str,
    artifact_id: str,
    *,
    domain_owner: str = "Data",
) -> dict[str, Any]:
    """Build one canonical MCP evidence reference payload."""
    return {
        "artifact_type": artifact_type,
        "artifact_id": artifact_id,
        "domain_owner": domain_owner,
        "uri": f"research://postgres/{artifact_type}/{artifact_id}",
    }
