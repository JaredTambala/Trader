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
from .data import DataInventoryRequest, get_data_inventory

__all__ = [
    "AGENT_DEFINITIONS",
    "TOOL_OWNER_BY_NAME",
    "AgentDefinition",
    "ArtifactReference",
    "DataInventoryRequest",
    "SideEffect",
    "ToolEnvelope",
    "agent_owner_for_tool",
    "envelope_json",
    "error_envelope",
    "get_data_inventory",
    "get_agent_definition",
    "success_envelope",
    "write_json_artifact",
]
