"""Research-agent service metadata.

This package holds deterministic research-domain services and contracts. The
initial skeleton exposes only ownership metadata; behavior is added in later
MCP tool slices.
"""

from .agents import (
    AGENT_DEFINITIONS,
    TOOL_OWNER_BY_NAME,
    AgentDefinition,
    agent_owner_for_tool,
    get_agent_definition,
)
from .contracts import (
    ArtifactReference,
    SideEffect,
    ToolEnvelope,
    envelope_json,
    error_envelope,
    success_envelope,
    write_json_artifact,
)
from .data import (
    DataInventoryRequest,
    DataProviderContext,
    DataSymbolDiscoveryRequest,
    data_discover_symbols,
    get_data_inventory,
    resolve_data_provider_context,
)
from .domain import (
    BoundedResearchRequest,
    DataRequirement,
    ResearchIssue,
    SpecialistArtifactSlot,
    SpecialistHandoff,
)

__all__ = [
    "AGENT_DEFINITIONS",
    "TOOL_OWNER_BY_NAME",
    "AgentDefinition",
    "ArtifactReference",
    "BoundedResearchRequest",
    "DataInventoryRequest",
    "DataProviderContext",
    "DataSymbolDiscoveryRequest",
    "DataRequirement",
    "ResearchIssue",
    "SideEffect",
    "SpecialistArtifactSlot",
    "SpecialistHandoff",
    "ToolEnvelope",
    "agent_owner_for_tool",
    "envelope_json",
    "error_envelope",
    "data_discover_symbols",
    "get_data_inventory",
    "get_agent_definition",
    "resolve_data_provider_context",
    "success_envelope",
    "write_json_artifact",
]
