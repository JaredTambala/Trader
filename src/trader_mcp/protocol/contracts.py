"""MCP transport envelopes for research application outcomes."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
import json
from typing import Any, Mapping, Sequence

from trader_research.foundation import ApplicationResult, jsonable
from trader_research.governance import agent_owner_for_tool


SCHEMA_VERSION = "1"

_READ_ONLY_OPERATIONS = frozenset(
    {
        "mcp_health",
        "mcp_get_config",
        "data_discover_symbols",
        "data_get_inventory",
        "data_summarize_quality",
        "knowledge_get_ingestion_status",
        "knowledge_list_sources",
        "knowledge_search_methods",
        "knowledge_list_method_card_sets",
        "knowledge_get_method_card_set",
        "knowledge_retrieve_evidence",
        "knowledge_get_evidence_chunks",
        "knowledge_validate_citations",
        "math_list_method_contracts",
        "math_validate_method_contract",
        "math_list_indicator_contracts",
        "math_validate_indicator_contract",
        "research_list_strategy_templates",
        "research_search_implementations",
        "research_get_implementation",
        "research_compare_implementation",
        "research_get_backtest_results",
        "research_list_risk_manager_templates",
        "coding_get_workspace",
        "coding_search_repository",
        "coding_read_repository_file",
        "coding_read_candidate_file",
        "coding_resolve_dependencies",
        "coding_package_candidate",
        "research_get_optimizer_runtime",
        "research_get_parameter_optimization_results",
        "research_get_agent_session",
        "research_get_agent_decision",
        "research_read_artifact",
    }
)
_EXTERNAL_RESEARCH_MUTATING_OPERATIONS = frozenset(
    {"research_project_experiment_tracking"}
)


class SideEffect(str, Enum):
    """Declared side-effect class for an MCP tool."""

    READ_ONLY = "read_only"
    LOCAL_MUTATING = "local_mutating"
    EXTERNAL_RESEARCH_MUTATING = "external_research_mutating"
    BROKER_READ = "broker_read"
    BROKER_MUTATING = "broker_mutating"


def side_effect_for_operation(operation: str) -> SideEffect:
    """Resolve MCP side-effect metadata for a registered research operation."""
    agent_owner_for_tool(operation)
    if operation in _READ_ONLY_OPERATIONS:
        return SideEffect.READ_ONLY
    if operation in _EXTERNAL_RESEARCH_MUTATING_OPERATIONS:
        return SideEffect.EXTERNAL_RESEARCH_MUTATING
    return SideEffect.LOCAL_MUTATING


@dataclass(frozen=True)
class ToolEnvelope:
    """Stable MCP wire envelope around a research operation result."""

    ok: bool
    command: str
    agent_owner: str
    side_effect: SideEffect
    data: Mapping[str, Any] = field(default_factory=dict)
    artifacts: Mapping[str, Any] = field(default_factory=dict)
    warnings: Sequence[str] = field(default_factory=tuple)
    errors: Sequence[Mapping[str, Any]] = field(default_factory=tuple)
    generated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    schema_version: str = SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        """Serialize the envelope to a JSON-compatible mapping."""
        return {
            "ok": self.ok,
            "command": self.command,
            "agent_owner": self.agent_owner,
            "side_effect": self.side_effect.value,
            "schema_version": self.schema_version,
            "generated_at": jsonable(self.generated_at),
            "data": jsonable(self.data),
            "artifacts": jsonable(self.artifacts),
            "warnings": list(self.warnings),
            "errors": jsonable(self.errors),
        }


def envelope_from_result(
    result: ApplicationResult,
    *,
    side_effect: SideEffect,
    agent_owner: str | None = None,
) -> ToolEnvelope:
    """Add MCP ownership and policy metadata to an application result."""
    return ToolEnvelope(
        ok=result.ok,
        command=result.operation,
        agent_owner=agent_owner or agent_owner_for_tool(result.operation),
        side_effect=side_effect,
        data=result.data,
        artifacts=result.artifacts,
        warnings=result.warnings,
        errors=result.errors,
        schema_version=result.schema_version,
    )


def result_to_envelope(result: ApplicationResult) -> ToolEnvelope:
    """Convert an application result using registered MCP policy metadata."""
    return envelope_from_result(
        result,
        side_effect=side_effect_for_operation(result.operation),
    )


def success_envelope(
    *,
    command: str,
    side_effect: SideEffect,
    agent_owner: str | None = None,
    data: Mapping[str, Any] | None = None,
    artifacts: Mapping[str, Any] | None = None,
    warnings: Sequence[str] | None = None,
) -> ToolEnvelope:
    """Build a successful MCP-owned operation envelope."""
    return ToolEnvelope(
        ok=True,
        command=command,
        agent_owner=agent_owner or agent_owner_for_tool(command),
        side_effect=side_effect,
        data=dict(data or {}),
        artifacts=dict(artifacts or {}),
        warnings=tuple(warnings or ()),
    )


def error_envelope(
    *,
    command: str,
    side_effect: SideEffect,
    message: str,
    agent_owner: str | None = None,
    code: str = "error",
    data: Mapping[str, Any] | None = None,
) -> ToolEnvelope:
    """Build a failed MCP-owned operation envelope."""
    return ToolEnvelope(
        ok=False,
        command=command,
        agent_owner=agent_owner or agent_owner_for_tool(command),
        side_effect=side_effect,
        data=dict(data or {}),
        errors=({"code": code, "message": message},),
    )


def envelope_json(envelope: ToolEnvelope) -> str:
    """Serialize an MCP envelope as stable pretty JSON."""
    return json.dumps(envelope.to_dict(), indent=2, sort_keys=True, default=str)
