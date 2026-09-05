"""Behavioral contracts for the exact admitted local Agent model.

Subject: Coordinator specialist selection, ambiguity handling, and Data readiness judgment by the pinned model.
Level: Opt-in local-model contract.
Collaborators: Real Ollama model calls with real Agent prompts/contracts and an in-memory Data MCP double.
Guarantees: The exact admitted model makes the minimum bounded decisions required by the current Agent slice.
Non-goals: General model quality, provider portability, full runtime execution, Postgres, and release acceptance.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from dataclasses import replace
import os
from typing import Any

import anyio
import pytest

from tests.trader_agents.contracts_state.support.agentic_scenarios import build_agentic_scenario_sessions
from trader_agents import (
    AgentPhase,
    AgentRole,
    AgendaTaskProposal,
    BudgetLedger,
    CanonicalEvidenceRef,
    CompositeDataScope,
    CoordinatorAgenda,
    DataResearchAgent,
    McpToolDescription,
    SpecialistDelegation,
    SpecialistReturn,
    SpecialistStatus,
    StructuredModelRunner,
    build_delegation,
    composite_data_scope_from_session,
    development_model_profiles,
    first_slice_programs,
    first_slice_tool_catalogue,
    profile_environment,
)
from trader_agents.coordination.coordinator import _propose_coordinator_agenda
from trader_agents.model_runtime.client import build_llm_client_from_env
from trader_research.governance import ResearchSession


_RUN_LOCAL_MODEL_CONTRACTS_ENV = "TRADER_RUN_LOCAL_MODEL_CONTRACTS"
_FIXED_REVISION = "a" * 40
pytestmark = [
    pytest.mark.local_model,
    pytest.mark.skipif(
        os.environ.get(_RUN_LOCAL_MODEL_CONTRACTS_ENV) != "1",
        reason=f"set {_RUN_LOCAL_MODEL_CONTRACTS_ENV}=1",
    ),
]


def test_coordinator_model_selects_only_data_for_readiness_briefs() -> None:
    """Equivalent Data-only briefs select Data and omit Strategy."""
    base_session = _scenario_session("exact_reuse")
    objectives = (
        (
            "Assess whether every item in the approved BTC/USD and ETH/USD "
            "hourly Data scope is ready for later research. Return only exact "
            "dataset-manifest and quality evidence; implementation work is "
            "outside this request."
        ),
        (
            "Inventory and quality-check the complete fixed multi-asset Data "
            "scope, using approved loading only if it is necessary. The sole "
            "deliverable is canonical Data-readiness evidence, not a strategy "
            "implementation."
        ),
        (
            "Establish the exact readiness of the session's two-asset hourly "
            "dataset and create its canonical snapshot evidence. Do not search "
            "for, adapt, or author implementation code."
        ),
    )
    sessions = tuple(
        replace(
            base_session,
            objective=objective,
            success_definition=(
                "Conclude only with canonical manifest and quality evidence for "
                "the complete approved Data scope; no implementation evidence "
                "is requested."
            ),
        )
        for objective in objectives
    )

    agendas = anyio.run(_run_agendas, sessions)

    assert len(agendas) == len(objectives)
    for agenda in agendas:
        assert agenda.material_ambiguities == []
        assert {task.role for task in agenda.tasks} == {AgentRole.DATA_RESEARCH.value}


def test_coordinator_model_interrupts_materially_ambiguous_brief() -> None:
    """A missing material strategy rule yields ambiguity without invented work."""
    agenda = anyio.run(
        _run_agenda,
        _scenario_session("material_ambiguity"),
    )

    assert agenda.material_ambiguities
    assert agenda.tasks == []


def test_data_model_judges_complete_multi_asset_scope_ready() -> None:
    """The Data model gathers sufficient evidence without loading or narrowing."""
    session = replace(
        _scenario_session("exact_reuse"),
        objective=(
            "Assess whether every item in the approved BTC/USD and ETH/USD "
            "hourly Data scope is ready for later research. Return only exact "
            "dataset-manifest and quality evidence."
        ),
        success_definition=(
            "Conclude only with canonical manifest and quality evidence for "
            "the complete approved Data scope."
        ),
    )
    scope = composite_data_scope_from_session(session)
    task = AgendaTaskProposal(
        task_id="assess-complete-data-scope",
        role=AgentRole.DATA_RESEARCH.value,
        scope_item_ids=[item.item_id for item in scope.items],
        question=(
            "Is every item in the approved multi-asset Data scope ready for "
            "the declared research use?"
        ),
        required_evidence=[
            "canonical dataset manifest",
            "canonical data quality report",
        ],
        expected_information_gain=(
            "Resolve complete-scope Data readiness from canonical evidence."
        ),
        mutation_requested=True,
    )
    delegation = build_delegation(
        session_id=session.session_id,
        branch_id="ready-data-model-contract",
        task=task,
        required_input_refs=[],
        permitted_side_effects=["read_only", "local_mutating"],
        reserved_model_calls=12,
        reserved_tool_calls=12,
        reserved_tokens=60_000,
        attempt=1,
    )
    mcp_client = _ReadyDataMcpClient(scope=scope)

    result = anyio.run(
        _run_data_agent,
        session,
        scope,
        delegation,
        mcp_client,
    )

    assert result.status is SpecialistStatus.READY, (
        [blocker.model_dump(mode="json") for blocker in result.blockers],
        [name for name, _ in mcp_client.calls],
    )
    assert {reference.uri for reference in result.evidence_refs} == {
        mcp_client.manifest_ref.uri,
        mcp_client.quality_ref.uri,
    }
    called_tools = [name for name, _ in mcp_client.calls]
    assert "data_get_inventory" in called_tools
    assert "data_summarize_quality" in called_tools
    assert "data_create_research_snapshot" in called_tools
    assert "data_ensure_loaded" not in called_tools
    for name, arguments in mcp_client.calls:
        if name in {
            "data_get_inventory",
            "data_summarize_quality",
            "data_create_research_snapshot",
        }:
            _assert_complete_scope(arguments, scope)


def _scenario_session(scenario_id: str) -> ResearchSession:
    """Return one credential-free scenario session for model-choice tests."""
    sessions = build_agentic_scenario_sessions(
        scenario_id,
        repetition=1,
        freeze_revision=_FIXED_REVISION,
        execution_namespace="campaign",
    )
    if len(sessions) != 1:
        raise AssertionError(f"{scenario_id} must provide exactly one session")
    return sessions[0]


async def _run_agendas(
    sessions: tuple[ResearchSession, ...],
) -> tuple[CoordinatorAgenda, ...]:
    """Invoke the exact agenda boundary for each supplied session."""
    agendas = []
    for session in sessions:
        agendas.append(await _run_agenda(session))
    return tuple(agendas)


async def _run_agenda(session: ResearchSession) -> CoordinatorAgenda:
    """Invoke the Coordinator model without MCP or specialist execution."""
    catalogue = first_slice_tool_catalogue()
    program = first_slice_programs().for_role(AgentRole.RESEARCH_COORDINATOR)
    profile = development_model_profiles().get(program.model_profile_id)
    client = build_llm_client_from_env(profile_environment(profile))
    result = await _propose_coordinator_agenda(
        model_runner=StructuredModelRunner(client),
        program=program,
        profile=profile,
        session=session,
        catalogue=catalogue,
        ledger=BudgetLedger(session.budget),
        branch_id="coordinator-model-contract",
    )
    return result.output


async def _run_data_agent(
    session: ResearchSession,
    scope: CompositeDataScope,
    delegation: SpecialistDelegation,
    mcp_client: "_ReadyDataMcpClient",
) -> SpecialistReturn:
    """Run the Data specialist with the real model and in-process evidence."""
    catalogue = first_slice_tool_catalogue()
    program = first_slice_programs().for_role(AgentRole.DATA_RESEARCH)
    profile = development_model_profiles().get(program.model_profile_id)
    agent = DataResearchAgent(
        model_runner=StructuredModelRunner(
            build_llm_client_from_env(profile_environment(profile))
        ),
        mcp_client=mcp_client,
        tool_catalogue=catalogue,
    )
    return await agent.run(
        session=session,
        delegation=delegation,
        scope=scope,
        program=program,
        profile=profile,
    )


@dataclass
class _ReadyDataMcpClient:
    """Deterministic in-process evidence boundary for a ready Data scope."""

    scope: CompositeDataScope
    manifest_ref: CanonicalEvidenceRef = field(
        default_factory=lambda: _evidence_ref(
            "dataset_manifest",
            "ready-data-manifest",
        )
    )
    quality_ref: CanonicalEvidenceRef = field(
        default_factory=lambda: _evidence_ref(
            "data_quality_report",
            "ready-data-quality",
        )
    )
    calls: list[tuple[str, dict[str, Any]]] = field(default_factory=list)

    async def list_tools(self) -> Sequence[McpToolDescription]:
        """Expose the complete code-owned Data catalogue with bounded schemas."""
        catalogue = first_slice_tool_catalogue()
        definitions = {
            definition.name: definition
            for phase in AgentPhase
            for definition in catalogue.available(
                role=AgentRole.DATA_RESEARCH,
                phase=phase,
                approval_policy={"data_loading": "preapproved_within_scope"},
            )
        }
        return tuple(
            McpToolDescription(
                name=definition.name,
                description=definition.description,
                input_schema=_data_tool_schema(definition.name),
            )
            for definition in sorted(definitions.values(), key=lambda item: item.name)
        )

    async def call_tool(
        self,
        tool_name: str,
        arguments: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        """Return complete inventory, quality, or canonical snapshot evidence."""
        copied_arguments = dict(arguments)
        self.calls.append((tool_name, copied_arguments))
        if tool_name == "data_ensure_loaded":
            raise AssertionError("ready Data must not invoke provider loading")
        definition = first_slice_tool_catalogue().resolve(
            AgentRole.DATA_RESEARCH,
            tool_name,
        )
        artifacts: dict[str, Any] = {}
        if tool_name == "data_get_inventory":
            data = {
                "coverage_status": "complete",
                "symbols": list(copied_arguments.get("symbols") or []),
                "start": copied_arguments.get("start"),
                "end": copied_arguments.get("end"),
                "missing_boundaries": [],
            }
        elif tool_name == "data_summarize_quality":
            data = {
                "quality_status": "passed",
                "symbols": list(copied_arguments.get("symbols") or []),
                "missing_intervals": [],
                "duplicate_timestamps": 0,
                "completeness_ratio": 1.0,
            }
        elif tool_name == "data_create_research_snapshot":
            data = {"snapshot_status": "created", "scope_status": "complete"}
            artifacts = {
                "dataset_manifest": _mcp_artifact(self.manifest_ref),
                "data_quality_report": _mcp_artifact(self.quality_ref),
            }
        elif tool_name == "data_discover_symbols":
            data = {
                "symbols": [
                    symbol for item in self.scope.items for symbol in item.symbols
                ]
            }
        elif tool_name in {"mcp_health", "mcp_get_config"}:
            data = {"status": "ok"}
        else:
            raise AssertionError(f"unexpected Data tool: {tool_name}")
        return {
            "structuredContent": {
                "ok": True,
                "command": tool_name,
                "agent_owner": definition.expected_owner,
                "side_effect": definition.side_effect.value,
                "data": data,
                "artifacts": artifacts,
                "warnings": [],
                "errors": [],
            },
            "isError": False,
        }


def _data_tool_schema(tool_name: str) -> dict[str, Any]:
    """Return a bounded production-shaped schema for one in-process tool."""
    if tool_name in {"mcp_health", "mcp_get_config"}:
        return {"type": "object", "additionalProperties": False}
    properties: dict[str, Any] = {
        "symbols": {"type": "array", "items": {"type": "string"}},
        "asset_class": {"type": "string"},
        "timeframe": {"type": "string"},
        "start": {"type": "string"},
        "end": {"type": "string"},
        "source": {"type": ["string", "null"]},
        "provider": {"type": ["string", "null"]},
        "instrument_type": {"type": ["string", "null"]},
        "bar_type": {"type": ["string", "null"]},
    }
    required = ["symbols", "asset_class", "timeframe", "start", "end"]
    if tool_name == "data_create_research_snapshot":
        properties.update(
            {
                "requested_by": {"type": "string"},
                "actor": {"type": "string"},
            }
        )
        required.extend(["requested_by", "actor"])
    if tool_name == "data_ensure_loaded":
        properties.update(
            {
                "mode": {"enum": ["sample", "backfill"]},
                "dry_run": {"type": "boolean"},
                "acquisition_plan_id": {"type": ["string", "null"]},
            }
        )
        required.extend(["mode", "dry_run"])
    if tool_name == "data_discover_symbols":
        return {
            "type": "object",
            "properties": properties,
            "additionalProperties": True,
        }
    return {
        "type": "object",
        "properties": properties,
        "required": required,
        "additionalProperties": False,
    }


def _evidence_ref(artifact_type: str, artifact_id: str) -> CanonicalEvidenceRef:
    """Build one stable canonical Data evidence reference."""
    return CanonicalEvidenceRef(
        artifact_type=artifact_type,
        artifact_id=artifact_id,
        domain_owner="Data",
        uri=f"research://postgres/{artifact_type}/{artifact_id}",
    )


def _mcp_artifact(reference: CanonicalEvidenceRef) -> dict[str, Any]:
    """Project one canonical reference into the MCP artifact envelope."""
    return {
        "artifact_type": reference.artifact_type,
        "path": None,
        "uri": reference.uri,
        "metadata": {
            "id": reference.artifact_id,
            "domain_owner": reference.domain_owner,
        },
    }


def _assert_complete_scope(
    arguments: Mapping[str, Any],
    scope: CompositeDataScope,
) -> None:
    """Assert one scoped call retained every approved multi-asset boundary."""
    assert len(scope.items) == 1
    item = scope.items[0]
    assert set(arguments.get("symbols") or []) == set(item.symbols)
    assert arguments.get("asset_class") == item.asset_class
    assert arguments.get("timeframe") == item.timeframe
    assert arguments.get("start") == item.start
    assert arguments.get("end") == item.end
