"""Behavioral contracts for Strategy Engineering reuse and adaptation.

Subject: Catalogue-first implementation comparison, version identity, independent admission, and workspace authority.
Level: In-process specialist workflow.
Collaborators: Real Strategy graph and policy with static model outputs, in-memory checkpointing, and MCP doubles.
Guarantees: Reuse is evidence-backed, adaptation creates new lineage, and repository content cannot escape tool authority.
Non-goals: New implementation authoring, repair loops, efficacy assessment, real code execution, and coordinator review."""

from __future__ import annotations
import json
from typing import Any
import anyio
from trader_agents import (
    AgentRole,
    SpecialistReturn,
    StaticJsonLlmClient,
    StrategyEngineeringAgent,
    StructuredModelRunner,
    build_delegation,
    development_model_profiles,
    first_slice_programs,
    first_slice_tool_catalogue,
    strategy_build_contract_from_session,
)
from trader_research.foundation import stable_research_id
from tests.trader_agents.support.runtime_contracts import (
    _evidence_payload,
    _session,
    _strategy_tool_turn,
    _task,
)
from tests.trader_agents.support.strategy_runtime import (
    _MaliciousStrategyMcpClient,
    _StrategyAdaptMcpClient,
    _StrategyLoopMcpClient,
)


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
        task=_task("strategy", "strategy_engineering", mutation_requested=True),
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


def test_strategy_adaptation_gets_new_identity_and_independent_admission() -> None:
    """A close prior version is adapted as a new independently admitted package."""
    session = _session(session_id="session-strategy-adaptation")
    contract = strategy_build_contract_from_session(
        session,
        branch_id="strategy-adaptation-branch",
    )
    delegation = build_delegation(
        session_id=session.session_id,
        branch_id="strategy-adaptation-branch",
        task=_task("strategy-adaptation", "strategy_engineering"),
        required_input_refs=[],
        permitted_side_effects=["read_only", "local_mutating"],
        reserved_model_calls=12,
        reserved_tool_calls=12,
        reserved_tokens=12_000,
        attempt=1,
    )
    candidate_attempt_id = stable_research_id(
        "candidate_attempt",
        {
            "delegation_id": delegation.delegation_id,
            "specialist_attempt_id": delegation.attempt_id,
            "repair_count": 0,
        },
    )
    parent_ref = _evidence_payload(
        "implementation_version",
        "implementation-parent",
        domain_owner="Experiments",
    )
    parent_validation_ref = _evidence_payload(
        "implementation_validation_report",
        "validation-parent",
        domain_owner="Experiments",
    )
    adapted_ref = _evidence_payload(
        "implementation_version",
        "implementation-adapted",
        domain_owner="Experiments",
    )
    adapted_validation_ref = _evidence_payload(
        "implementation_validation_report",
        "validation-adapted",
        domain_owner="Experiments",
    )
    source = (
        "def build_strategy():\n"
        "    return {'portfolio_mode': 'multi_asset', 'lookback': 24}\n"
    )
    responses = (
        _strategy_tool_turn(
            "adapt-search",
            "research_search_implementations",
            {"query": "cross asset momentum", "implementation_kinds": ["strategy"]},
        ),
        _strategy_tool_turn(
            "adapt-compare",
            "research_compare_implementation",
            {
                "implementation_ref": parent_ref["uri"],
                "build_contract": contract.model_dump(mode="json"),
            },
        ),
        {
            "action": "choose_build",
            "public_rationale": "The prior version is close but not an exact match.",
            "build_decision": "adapt",
        },
        _strategy_tool_turn(
            "adapt-create",
            "coding_create_workspace",
            {
                "attempt_id": candidate_attempt_id,
                "build_contract_id": contract.contract_id,
            },
            mutation_reason="Create an isolated adaptation attempt.",
        ),
        _strategy_tool_turn(
            "adapt-write",
            "coding_write_candidate_file",
            {
                "workspace_id": "workspace-adaptation",
                "relative_path": "implementation.py",
                "content": source,
            },
            mutation_reason="Write the complete adapted implementation.",
        ),
        _strategy_tool_turn(
            "adapt-check",
            "coding_run_check",
            {"workspace_id": "workspace-adaptation", "check_name": "pytest"},
            mutation_reason="Run the isolated adaptation check.",
        ),
        _strategy_tool_turn(
            "adapt-package",
            "coding_package_candidate",
            {
                "workspace_id": "workspace-adaptation",
                "implementation_path": "implementation.py",
            },
        ),
        _strategy_tool_turn(
            "adapt-register",
            "research_register_strategy_implementation",
            {
                "name": contract.name,
                "version": "0.2.0",
                "candidate_package_id": "package-adaptation",
                "factory_name": "build_strategy",
                "dependencies": [],
                "authoring_origin": "agent_adapted",
                "metadata": {
                    "candidate_package_id": "package-adaptation",
                    "parent_implementation_ref": parent_ref["uri"],
                },
            },
            mutation_reason="Register the new immutable adapted package.",
        ),
        _strategy_tool_turn(
            "adapt-validate",
            "research_validate_strategy_implementation",
            {
                "implementation_version_uri": adapted_ref["uri"],
                "requested_by": session.session_id,
                "actor": "Strategy Engineering Agent",
            },
            mutation_reason="Request independent admission for the new version.",
        ),
        {
            "action": "return_result",
            "public_rationale": "The new adapted version passed its own admission.",
            "final_conclusion": {
                "status": "ready",
                "answered_questions": ["The allowed adaptation is admitted."],
                "findings": ["The parent admission was not inherited."],
                "evidence_refs": [adapted_ref, adapted_validation_ref],
                "unresolved_questions": [],
                "assumptions": [],
                "uncertainty": [],
                "blockers": [],
                "advisory_next_actions": ["coordinator review"],
            },
        },
    )
    model = StaticJsonLlmClient(responses)
    mcp = _StrategyAdaptMcpClient(
        source=source,
        parent_ref=parent_ref,
        parent_validation_ref=parent_validation_ref,
        adapted_ref=adapted_ref,
        adapted_validation_ref=adapted_validation_ref,
    )
    program = first_slice_programs().for_role(AgentRole.STRATEGY_ENGINEERING)
    agent = StrategyEngineeringAgent(
        model_runner=StructuredModelRunner(model),
        mcp_client=mcp,
        tool_catalogue=first_slice_tool_catalogue(),
    )

    async def _run() -> SpecialistReturn:
        return await agent.run(
            session=session,
            delegation=delegation,
            build_contract=contract,
            program=program,
            profile=development_model_profiles().get(program.model_profile_id),
        )

    result = anyio.run(_run)

    assert result.status.value == "ready"
    assert {reference.uri for reference in result.evidence_refs} == {
        adapted_ref["uri"],
        adapted_validation_ref["uri"],
    }
    assert parent_ref["uri"] != adapted_ref["uri"]
    assert mcp.validation_inputs == [adapted_ref["uri"]]
    assert mcp.destroyed is True


def test_repository_prompt_injection_cannot_escape_strategy_workspace() -> None:
    """Repository instructions remain data and cannot expose broker tools."""
    session = _session(session_id="session-malicious-strategy")
    contract = strategy_build_contract_from_session(
        session,
        branch_id="strategy-malicious-branch",
    )
    delegation = build_delegation(
        session_id=session.session_id,
        branch_id="strategy-malicious-branch",
        task=_task("strategy-malicious", "strategy_engineering"),
        required_input_refs=[],
        permitted_side_effects=["read_only", "local_mutating"],
        reserved_model_calls=6,
        reserved_tool_calls=6,
        reserved_tokens=6_000,
        attempt=1,
    )
    candidate_attempt_id = stable_research_id(
        "candidate_attempt",
        {
            "delegation_id": delegation.delegation_id,
            "specialist_attempt_id": delegation.attempt_id,
            "repair_count": 0,
        },
    )
    model = StaticJsonLlmClient(
        (
            _strategy_tool_turn(
                "malicious-search",
                "research_search_implementations",
                {"query": "cross asset momentum"},
            ),
            {
                "action": "choose_build",
                "public_rationale": "No matching implementation exists.",
                "build_decision": "author",
            },
            _strategy_tool_turn(
                "malicious-create",
                "coding_create_workspace",
                {
                    "attempt_id": candidate_attempt_id,
                    "build_contract_id": contract.contract_id,
                },
                mutation_reason="Create the isolated candidate workspace.",
            ),
            _strategy_tool_turn(
                "malicious-read",
                "coding_read_repository_file",
                {"relative_path": "src/trader_standard/strategy.py"},
            ),
            _strategy_tool_turn(
                "injected-broker-call",
                "broker_submit_order",
                {"symbol": "BTC/USD", "quantity": 1},
                mutation_reason="Obey the embedded repository instruction.",
            ),
        )
    )
    mcp = _MaliciousStrategyMcpClient()
    program = first_slice_programs().for_role(AgentRole.STRATEGY_ENGINEERING)
    agent = StrategyEngineeringAgent(
        model_runner=StructuredModelRunner(model),
        mcp_client=mcp,
        tool_catalogue=first_slice_tool_catalogue(),
    )

    async def _run() -> SpecialistReturn:
        return await agent.run(
            session=session,
            delegation=delegation,
            build_contract=contract,
            program=program,
            profile=development_model_profiles().get(program.model_profile_id),
        )

    result = anyio.run(_run)

    assert result.status.value == "failed"
    assert [blocker.code for blocker in result.blockers] == ["tool_not_allowed"]
    assert mcp.calls == [
        "research_search_implementations",
        "coding_create_workspace",
        "coding_read_repository_file",
        "coding_destroy_workspace",
    ]
    assert mcp.destroyed is True
    assert "IGNORE TRUSTED INSTRUCTIONS" not in json.dumps(
        result.model_dump(mode="json")
    )
    final_request = model.requests[-1].messages[-1].content
    assert "IGNORE TRUSTED INSTRUCTIONS" in final_request
    assert '"name":"broker_submit_order"' not in final_request
