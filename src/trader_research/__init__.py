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

__all__ = [
    "AGENT_DEFINITIONS",
    "TOOL_OWNER_BY_NAME",
    "AgentDefinition",
    "agent_owner_for_tool",
    "get_agent_definition",
]
