"""Versioned role- and state-scoped MCP catalogue for model-backed agents."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from trader_mcp.catalogue.definitions import (
    AGENTIC_TOOL_DESCRIPTIONS,
    CODING_TOOL_DESCRIPTIONS,
    DATA_TOOL_DESCRIPTIONS,
    MCP_CONFIG_TOOL,
    MCP_HEALTH_TOOL,
    RESEARCH_TOOL_DESCRIPTIONS,
    SUPPORT_TOOL_DESCRIPTIONS,
)
from trader_mcp.protocol.contracts import SideEffect, side_effect_for_operation
from trader_research.foundation import json_payload_hash

from trader_agents.contracts.domain import AgentPhase, AgentRole


@dataclass(frozen=True)
class ToolDefinition:
    """Code-owned policy metadata for one model-visible MCP operation.

    Attributes:
        name: Exact registered MCP tool name.
        role: Model-backed role allowed to propose the operation.
        expected_owner: Required MCP envelope stewardship label.
        description: Public model-facing operation description.
        side_effect: Maximum declared MCP side effect.
        phases: Invocation phases where the operation may be exposed.
        approval_key: Optional session approval-policy key required for exposure.
    """

    name: str
    role: AgentRole
    expected_owner: str
    description: str
    side_effect: SideEffect
    phases: tuple[AgentPhase, ...]
    approval_key: str | None = None

    def __post_init__(self) -> None:
        """Reject unsafe side effects and incomplete definitions."""
        if not self.name or not self.expected_owner or not self.description:
            raise ValueError("tool definition identity and description are required")
        if not self.phases:
            raise ValueError("tool definition phases are required")
        if self.side_effect in {SideEffect.BROKER_READ, SideEffect.BROKER_MUTATING}:
            raise ValueError("broker tools cannot enter the research-agent catalogue")

    def to_dict(self) -> dict[str, Any]:
        """Return stable public catalogue metadata."""
        return {
            "name": self.name,
            "role": self.role.value,
            "expected_owner": self.expected_owner,
            "description": self.description,
            "side_effect": self.side_effect.value,
            "phases": [phase.value for phase in self.phases],
            "approval_key": self.approval_key,
        }


class ToolCatalogue:
    """Immutable exact lookup and dynamic narrowing for agent MCP tools."""

    def __init__(self, definitions: Iterable[ToolDefinition]) -> None:
        """Build a unique catalogue.

        Args:
            definitions: Code-owned operation definitions.
        """
        values = tuple(definitions)
        by_role_and_name = {
            (definition.role, definition.name): definition for definition in values
        }
        if len(by_role_and_name) != len(values):
            raise ValueError("tool definitions must be unique per role and name")
        self._definitions = values
        self._by_role_and_name = by_role_and_name

    @property
    def catalogue_id(self) -> str:
        """Return the content digest identifying this exact catalogue."""
        return json_payload_hash(self.public_manifest()["tools"])

    def resolve(self, role: AgentRole, tool_name: str) -> ToolDefinition:
        """Resolve one exact role-owned tool definition."""
        try:
            return self._by_role_and_name[(role, tool_name)]
        except KeyError as exc:
            raise KeyError(
                f"tool {tool_name!r} is not registered for role {role.value}"
            ) from exc

    def available(
        self,
        *,
        role: AgentRole,
        phase: AgentPhase,
        approval_policy: Mapping[str, Any],
    ) -> tuple[ToolDefinition, ...]:
        """Return the deterministic phase- and approval-narrowed catalogue.

        Args:
            role: Active model-backed role.
            phase: Current invocation phase.
            approval_policy: Immutable session approval-policy mapping.

        Returns:
            Sorted tool definitions safe to expose to the model.
        """
        available = []
        for definition in self._definitions:
            if definition.role is not role or phase not in definition.phases:
                continue
            if definition.approval_key is not None:
                if not _approval_granted(approval_policy.get(definition.approval_key)):
                    continue
            available.append(definition)
        return tuple(sorted(available, key=lambda item: item.name))

    def public_manifest(self) -> dict[str, Any]:
        """Return the complete sorted catalogue manifest."""
        tools = [
            definition.to_dict()
            for definition in sorted(
                self._definitions,
                key=lambda item: (item.role.value, item.name),
            )
        ]
        return {"tools": tools}


def first_slice_tool_catalogue() -> ToolCatalogue:
    """Build the selected Coordinator, Data, and Strategy MCP catalogue."""
    definitions = [
        *_support_definitions(AgentRole.RESEARCH_COORDINATOR),
        *_support_definitions(AgentRole.DATA_RESEARCH),
        *_support_definitions(AgentRole.STRATEGY_ENGINEERING),
        *_coordinator_definitions(),
        *_data_definitions(),
        *_strategy_definitions(),
    ]
    return ToolCatalogue(definitions)


def _support_definitions(role: AgentRole) -> list[ToolDefinition]:
    """Return read-only MCP support tools for one role."""
    phases = tuple(AgentPhase)
    return [
        ToolDefinition(
            name=name,
            role=role,
            expected_owner="MCP Server",
            description=SUPPORT_TOOL_DESCRIPTIONS[name],
            side_effect=SideEffect.READ_ONLY,
            phases=phases,
        )
        for name in (MCP_HEALTH_TOOL, MCP_CONFIG_TOOL)
    ]


def _coordinator_definitions() -> list[ToolDefinition]:
    """Return the narrow canonical-evidence control surface."""
    tools = {
        "research_create_agent_session": (AgentPhase.INTERPRET,),
        "research_get_agent_session": tuple(AgentPhase),
        "research_record_agent_decision": (
            AgentPhase.REVIEW,
            AgentPhase.AWAITING_OPERATOR,
            AgentPhase.TERMINAL,
        ),
        "research_get_agent_decision": (
            AgentPhase.REVIEW,
            AgentPhase.AWAITING_OPERATOR,
            AgentPhase.TERMINAL,
        ),
        "research_read_artifact": (
            AgentPhase.INTERPRET,
            AgentPhase.REVIEW,
            AgentPhase.TERMINAL,
        ),
    }
    return [
        ToolDefinition(
            name=name,
            role=AgentRole.RESEARCH_COORDINATOR,
            expected_owner="Research Coordinator",
            description=AGENTIC_TOOL_DESCRIPTIONS[name],
            side_effect=side_effect_for_operation(name),
            phases=phases,
        )
        for name, phases in tools.items()
    ]


def _data_definitions() -> list[ToolDefinition]:
    """Return Data Research investigation and remediation capabilities."""
    phases = {
        "data_discover_symbols": (AgentPhase.INVESTIGATE, AgentPhase.REMEDIATE),
        "data_get_inventory": (AgentPhase.INVESTIGATE, AgentPhase.REMEDIATE),
        "data_summarize_quality": (AgentPhase.INVESTIGATE, AgentPhase.REMEDIATE),
        "data_ensure_loaded": (AgentPhase.REMEDIATE,),
        "data_create_research_snapshot": (AgentPhase.REMEDIATE, AgentPhase.REVIEW),
    }
    return [
        ToolDefinition(
            name=name,
            role=AgentRole.DATA_RESEARCH,
            expected_owner="Data Agent",
            description=DATA_TOOL_DESCRIPTIONS[name],
            side_effect=side_effect_for_operation(name),
            phases=tool_phases,
            approval_key=("data_loading" if name == "data_ensure_loaded" else None),
        )
        for name, tool_phases in phases.items()
    ]


def _strategy_definitions() -> list[ToolDefinition]:
    """Return catalogue, workspace, packaging, and admission capabilities."""
    phase_by_name = {
        "research_list_strategy_templates": (AgentPhase.INVESTIGATE,),
        "research_list_risk_manager_templates": (AgentPhase.INVESTIGATE,),
        "research_search_implementations": (AgentPhase.INVESTIGATE,),
        "research_get_implementation": (AgentPhase.INVESTIGATE,),
        "research_compare_implementation": (AgentPhase.INVESTIGATE,),
        "coding_create_workspace": (AgentPhase.CONSTRUCT,),
        "coding_get_workspace": (AgentPhase.CONSTRUCT, AgentPhase.ADMIT),
        "coding_search_repository": (AgentPhase.CONSTRUCT,),
        "coding_read_repository_file": (AgentPhase.CONSTRUCT,),
        "coding_write_candidate_file": (AgentPhase.CONSTRUCT,),
        "coding_read_candidate_file": (AgentPhase.CONSTRUCT,),
        "coding_resolve_dependencies": (AgentPhase.CONSTRUCT,),
        "coding_run_check": (AgentPhase.CONSTRUCT,),
        "coding_package_candidate": (AgentPhase.CONSTRUCT,),
        "coding_destroy_workspace": (
            AgentPhase.CONSTRUCT,
            AgentPhase.ADMIT,
            AgentPhase.TERMINAL,
        ),
        "research_register_strategy_implementation": (AgentPhase.ADMIT,),
        "research_validate_strategy_implementation": (AgentPhase.ADMIT,),
        "research_register_risk_manager_implementation": (AgentPhase.ADMIT,),
        "research_validate_risk_manager_implementation": (AgentPhase.ADMIT,),
    }
    descriptions = {**RESEARCH_TOOL_DESCRIPTIONS, **CODING_TOOL_DESCRIPTIONS}
    return [
        ToolDefinition(
            name=name,
            role=AgentRole.STRATEGY_ENGINEERING,
            expected_owner="Strategy Engineering Agent",
            description=descriptions[name],
            side_effect=side_effect_for_operation(name),
            phases=phases,
            approval_key=("coding_workspace" if name.startswith("coding_") else None),
        )
        for name, phases in phase_by_name.items()
    ]


def _approval_granted(value: object) -> bool:
    """Normalize explicit session approval-policy values."""
    if value is True:
        return True
    if isinstance(value, str):
        return value.strip().lower() in {
            "approved",
            "allowed",
            "preapproved",
            "preapproved_within_scope",
            "true",
        }
    return False
