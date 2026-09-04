"""Behavioral contracts for Strategy Engineering authoring and repair.

Subject: Isolated candidate construction, validation, admission, cleanup, bounded repair, and loop termination.
Level: In-process specialist workflow.
Collaborators: Real Strategy graph and policy with static model outputs, in-memory checkpointing, and MCP doubles.
Guarantees: Authored candidates follow custody rules, actionable failures create new attempts, and equivalent failures stop.
Non-goals: Real container execution, efficacy claims, coordinator review, provider models, and deployment."""

from __future__ import annotations
from collections.abc import Mapping
from dataclasses import replace
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
from trader_research.governance import AgentBudget
from tests.trader_agents.support.runtime_contracts import (
    _evidence_payload,
    _session,
    _strategy_tool_turn,
    _task,
)
from tests.trader_agents.support.strategy_runtime import (
    _StrategyBuildMcpClient,
    _StrategyRepairMcpClient,
)


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
        '    """Return a deterministic candidate marker."""\n'
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
                "candidate_package_id": "package-author-1",
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


def test_strategy_loop_repairs_actionable_failed_admission_in_new_attempt() -> None:
    """Failed admission is cleaned up before one bounded new candidate attempt."""
    session = replace(
        _session(session_id="session-strategy-repair"),
        budget=AgentBudget(
            max_model_calls=24,
            max_tool_calls=24,
            max_tokens=24_000,
            max_duration_seconds=600,
            max_mutations=20,
            max_revisions=2,
            concurrency_limit=2,
        ),
    )
    contract = strategy_build_contract_from_session(
        session,
        branch_id="strategy-repair-branch",
    )
    delegation = build_delegation(
        session_id=session.session_id,
        branch_id="strategy-repair-branch",
        task=_task("strategy-repair", "strategy_engineering"),
        required_input_refs=[],
        permitted_side_effects=["read_only", "local_mutating"],
        reserved_model_calls=24,
        reserved_tool_calls=24,
        reserved_tokens=12_000,
        attempt=1,
    )
    candidate_attempts = [
        stable_research_id(
            "candidate_attempt",
            {
                "delegation_id": delegation.delegation_id,
                "specialist_attempt_id": delegation.attempt_id,
                "repair_count": repair_count,
            },
        )
        for repair_count in (0, 1)
    ]
    implementation_refs = [
        _evidence_payload(
            "implementation_version",
            f"implementation-repair-{index}",
            domain_owner="Experiments",
        )
        for index in (1, 2)
    ]
    validation_refs = [
        _evidence_payload(
            "implementation_validation_report",
            f"validation-repair-{index}",
            domain_owner="Experiments",
        )
        for index in (1, 2)
    ]
    responses: list[Mapping[str, Any]] = [
        _strategy_tool_turn(
            "repair-search",
            "research_search_implementations",
            {"query": "cross asset momentum", "implementation_kinds": ["strategy"]},
        ),
        {
            "action": "choose_build",
            "public_rationale": "No prior implementation matches the contract.",
            "build_decision": "author",
        },
    ]
    for index, workspace_id in enumerate(("workspace-repair-1", "workspace-repair-2")):
        package_id = f"package-repair-{index + 1}"
        responses.extend(
            [
                _strategy_tool_turn(
                    f"create-{index}",
                    "coding_create_workspace",
                    {
                        "attempt_id": candidate_attempts[index],
                        "build_contract_id": contract.contract_id,
                    },
                    mutation_reason="Create an isolated candidate attempt.",
                ),
                _strategy_tool_turn(
                    f"write-{index}",
                    "coding_write_candidate_file",
                    {
                        "workspace_id": workspace_id,
                        "relative_path": "implementation.py",
                        "content": (
                            "def build_strategy():\n"
                            f"    return {{'revision': {index}}}\n"
                        ),
                    },
                    mutation_reason="Write the complete candidate source.",
                ),
                _strategy_tool_turn(
                    f"check-{index}",
                    "coding_run_check",
                    {"workspace_id": workspace_id, "check_name": "pytest"},
                    mutation_reason="Run the isolated candidate check.",
                ),
                _strategy_tool_turn(
                    f"package-{index}",
                    "coding_package_candidate",
                    {
                        "workspace_id": workspace_id,
                        "implementation_path": "implementation.py",
                    },
                ),
                _strategy_tool_turn(
                    f"register-{index}",
                    "research_register_strategy_implementation",
                    {
                        "name": contract.name,
                        "version": f"0.1.{index}",
                        "candidate_package_id": package_id,
                        "factory_name": "build_strategy",
                        "dependencies": [],
                        "authoring_origin": "agent_authored",
                        "metadata": {"candidate_package_id": package_id},
                    },
                    mutation_reason="Register the exact candidate package.",
                ),
                _strategy_tool_turn(
                    f"validate-{index}",
                    "research_validate_strategy_implementation",
                    {
                        "implementation_version_uri": implementation_refs[index]["uri"],
                        "requested_by": session.session_id,
                        "actor": "Strategy Engineering Agent",
                    },
                    mutation_reason="Request independent deterministic admission.",
                ),
            ]
        )
        if index == 0:
            responses.append(
                {
                    "action": "change_phase",
                    "public_rationale": (
                        "The admission finding is actionable without changing "
                        "the accepted build contract."
                    ),
                    "next_phase": "construct",
                }
            )
    responses.append(
        {
            "action": "return_result",
            "public_rationale": "The repaired candidate passed independent admission.",
            "final_conclusion": {
                "status": "ready",
                "answered_questions": ["A repaired candidate was admitted."],
                "findings": [
                    "The first attempt failed and the second passed admission."
                ],
                "evidence_refs": [implementation_refs[1], validation_refs[1]],
                "unresolved_questions": [],
                "assumptions": [],
                "uncertainty": [],
                "blockers": [],
                "advisory_next_actions": ["coordinator review"],
            },
        }
    )
    mcp = _StrategyRepairMcpClient(
        implementation_refs=implementation_refs,
        validation_refs=validation_refs,
    )
    program = first_slice_programs().for_role(AgentRole.STRATEGY_ENGINEERING)
    agent = StrategyEngineeringAgent(
        model_runner=StructuredModelRunner(StaticJsonLlmClient(responses)),
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
    assert result.budget_used.revisions == 1
    assert mcp.validation_calls == 2
    assert mcp.destroyed_workspaces == [
        "workspace-repair-1",
        "workspace-repair-2",
    ]
    assert [
        call["attempt_id"]
        for name, call in mcp.calls
        if name == "coding_create_workspace"
    ] == candidate_attempts
    attributed_calls = [
        call
        for name, call in mcp.calls
        if name
        in {
            "research_register_strategy_implementation",
            "research_validate_strategy_implementation",
        }
    ]
    assert attributed_calls
    assert all(
        call["requested_by"] == session.session_id
        and call["actor"] == "Strategy Engineering Agent"
        for call in attributed_calls
    )


def test_strategy_loop_stops_after_irreparable_equivalent_admissions() -> None:
    """A second equivalent admission failure exhausts the repair authority."""
    session = replace(
        _session(session_id="session-strategy-irreparable"),
        budget=AgentBudget(
            max_model_calls=24,
            max_tool_calls=24,
            max_tokens=24_000,
            max_duration_seconds=600,
            max_mutations=20,
            max_revisions=2,
            concurrency_limit=2,
        ),
    )
    contract = strategy_build_contract_from_session(
        session,
        branch_id="strategy-irreparable-branch",
    )
    delegation = build_delegation(
        session_id=session.session_id,
        branch_id="strategy-irreparable-branch",
        task=_task("strategy-irreparable", "strategy_engineering"),
        required_input_refs=[],
        permitted_side_effects=["read_only", "local_mutating"],
        reserved_model_calls=24,
        reserved_tool_calls=24,
        reserved_tokens=12_000,
        attempt=1,
    )
    candidate_attempts = [
        stable_research_id(
            "candidate_attempt",
            {
                "delegation_id": delegation.delegation_id,
                "specialist_attempt_id": delegation.attempt_id,
                "repair_count": repair_count,
            },
        )
        for repair_count in (0, 1)
    ]
    implementation_refs = [
        _evidence_payload(
            "implementation_version",
            f"implementation-irreparable-{index}",
            domain_owner="Experiments",
        )
        for index in (1, 2)
    ]
    validation_refs = [
        _evidence_payload(
            "implementation_validation_report",
            f"validation-irreparable-{index}",
            domain_owner="Experiments",
        )
        for index in (1, 2)
    ]
    responses: list[Mapping[str, Any]] = [
        _strategy_tool_turn(
            "irreparable-search",
            "research_search_implementations",
            {"query": "cross asset momentum", "implementation_kinds": ["strategy"]},
        ),
        {
            "action": "choose_build",
            "public_rationale": "No prior implementation matches the contract.",
            "build_decision": "author",
        },
    ]
    for index, workspace_id in enumerate(("workspace-repair-1", "workspace-repair-2")):
        package_id = f"package-repair-{index + 1}"
        responses.extend(
            [
                _strategy_tool_turn(
                    f"irreparable-create-{index}",
                    "coding_create_workspace",
                    {
                        "attempt_id": candidate_attempts[index],
                        "build_contract_id": contract.contract_id,
                    },
                    mutation_reason="Create an isolated candidate attempt.",
                ),
                _strategy_tool_turn(
                    f"irreparable-write-{index}",
                    "coding_write_candidate_file",
                    {
                        "workspace_id": workspace_id,
                        "relative_path": "implementation.py",
                        "content": (
                            "def build_strategy():\n"
                            f"    return {{'revision': {index}}}\n"
                        ),
                    },
                    mutation_reason="Write the complete candidate source.",
                ),
                _strategy_tool_turn(
                    f"irreparable-check-{index}",
                    "coding_run_check",
                    {"workspace_id": workspace_id, "check_name": "pytest"},
                    mutation_reason="Run the isolated candidate check.",
                ),
                _strategy_tool_turn(
                    f"irreparable-package-{index}",
                    "coding_package_candidate",
                    {
                        "workspace_id": workspace_id,
                        "implementation_path": "implementation.py",
                    },
                ),
                _strategy_tool_turn(
                    f"irreparable-register-{index}",
                    "research_register_strategy_implementation",
                    {
                        "name": contract.name,
                        "version": f"0.2.{index}",
                        "candidate_package_id": package_id,
                        "factory_name": "build_strategy",
                        "dependencies": [],
                        "authoring_origin": "agent_authored",
                        "metadata": {"candidate_package_id": package_id},
                    },
                    mutation_reason="Register the exact candidate package.",
                ),
                _strategy_tool_turn(
                    f"irreparable-validate-{index}",
                    "research_validate_strategy_implementation",
                    {
                        "implementation_version_uri": implementation_refs[index]["uri"],
                        "requested_by": session.session_id,
                        "actor": "Strategy Engineering Agent",
                    },
                    mutation_reason="Request independent deterministic admission.",
                ),
                {
                    "action": "change_phase",
                    "public_rationale": (
                        "Attempt another repair without changing the contract."
                    ),
                    "next_phase": "construct",
                },
            ]
        )
    mcp = _StrategyRepairMcpClient(
        implementation_refs=implementation_refs,
        validation_refs=validation_refs,
        validation_outcomes=(False, False),
    )
    program = first_slice_programs().for_role(AgentRole.STRATEGY_ENGINEERING)
    agent = StrategyEngineeringAgent(
        model_runner=StructuredModelRunner(StaticJsonLlmClient(responses)),
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
    assert result.budget_used.revisions == 1
    assert [blocker.code for blocker in result.blockers] == [
        "candidate_repair_exhausted"
    ]
    assert mcp.validation_calls == 2
    assert mcp.destroyed_workspaces == [
        "workspace-repair-1",
        "workspace-repair-2",
    ]
    assert {reference.uri for reference in result.evidence_refs} == {
        reference["uri"] for reference in (*implementation_refs, *validation_refs)
    }
