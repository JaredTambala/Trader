"""Shared public-contract builders for Agent package tests.

Subject: Reusable session, budget, task, correlation, turn, and MCP-envelope fixtures.
Level: Test support.
Collaborators: Real immutable Agent and research contract types; no runtime or external service.
Guarantees: Test contexts construct the same bounded identities and payload shapes without hidden defaults.
Non-goals: Runtime execution, policy decisions, persistence, provider calls, and behavioral assertions.
Cohesion rationale: Every helper constructs the common public values shared across multiple Agent responsibilities."""

from __future__ import annotations
from collections.abc import Mapping
from typing import Any
from trader_agents import (
    AgentRole,
    AgendaTaskProposal,
    CompositeDataScope,
    DataInputRole,
    DataScopeItem,
    ParameterContract,
    TraceCorrelation,
    first_slice_programs,
    first_slice_tool_catalogue,
)
from trader_research.governance import AgentBudget, ResearchSession


def _session(*, session_id: str = "session-foundation") -> ResearchSession:
    """Build one complete first-slice session fixture."""
    catalogue = first_slice_tool_catalogue()
    programs = first_slice_programs()
    return ResearchSession(
        session_id=session_id,
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
                session_id=session_id,
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
            "runtime_interface": "trader.strategies.Strategy",
            "portfolio_mode": "multi_asset",
            "required_capabilities": [
                "multi_asset",
                "target_allocations",
                "completed_bar_momentum",
            ],
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
        model_profile_id="ollama-lfm25-8b-json-v1",
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
    work_kind: str = "complete",
    join_mode: str = "hard",
    scope_item_ids: list[str] | None = None,
) -> AgendaTaskProposal:
    """Build one visible agenda task fixture."""
    return AgendaTaskProposal(
        task_id=task_id,
        role=role,  # type: ignore[arg-type]
        work_kind=work_kind,  # type: ignore[arg-type]
        join_mode=join_mode,  # type: ignore[arg-type]
        scope_item_ids=scope_item_ids or [],
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
        model_profile_id="ollama-lfm25-8b-json-v1",
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


def _mcp_artifacts(
    artifacts: Mapping[str, Any],
) -> dict[str, Any]:
    """Project strict evidence refs into the public MCP artifact shape."""
    projected: dict[str, Any] = {}
    for label, raw in artifacts.items():
        if not isinstance(raw, Mapping):
            projected[label] = raw
            continue
        uri = str(raw.get("uri") or "")
        if not uri.startswith("research://postgres/"):
            projected[label] = dict(raw)
            continue
        projected[label] = {
            "artifact_type": raw["artifact_type"],
            "path": None,
            "uri": uri,
            "metadata": {
                "id": raw["artifact_id"],
                "domain_owner": raw["domain_owner"],
                "source_hash": raw.get("source_hash"),
            },
        }
    return projected
