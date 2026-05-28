"""Stdio MCP server skeleton for research tools."""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP
from mcp.types import CallToolResult

from trader_mcp.adapters import envelope_to_mcp_result
from trader_mcp.constants import (
    MCP_CONFIG_TOOL,
    MCP_HEALTH_TOOL,
    MCP_SERVER_OWNER,
    SERVER_NAME,
    SUPPORT_TOOL_DESCRIPTIONS,
    SUPPORT_TOOL_NAMES,
    UNREGISTERED_CAPABILITY_FLAGS,
)
from trader_mcp.environment import McpEnvironment, load_local_environment
from trader_research.contracts import SCHEMA_VERSION, SideEffect, ToolEnvelope, success_envelope


def create_server(environment: McpEnvironment | None = None) -> FastMCP:
    """Create the MCP server and register read-only support tools.

    Args:
        environment: Optional resolved local MCP environment.

    Returns:
        Configured FastMCP server instance.
    """
    local_env = environment or load_local_environment()
    server = FastMCP(SERVER_NAME)

    @server.tool(name=MCP_HEALTH_TOOL, description=SUPPORT_TOOL_DESCRIPTIONS[MCP_HEALTH_TOOL])
    def mcp_health() -> CallToolResult:
        """Return read-only MCP server health.

        Returns:
            MCP call result containing a read-only health envelope.
        """
        return CallToolResult(**envelope_to_mcp_result(build_health_envelope(local_env)))

    @server.tool(name=MCP_CONFIG_TOOL, description=SUPPORT_TOOL_DESCRIPTIONS[MCP_CONFIG_TOOL])
    def mcp_get_config() -> CallToolResult:
        """Return read-only MCP server configuration.

        Returns:
            MCP call result containing a read-only configuration envelope.
        """
        return CallToolResult(**envelope_to_mcp_result(build_config_envelope(local_env)))

    return server


def build_health_envelope(environment: McpEnvironment | None = None) -> ToolEnvelope:
    """Build the read-only MCP server health envelope.

    Args:
        environment: Optional resolved local MCP environment.

    Returns:
        Successful health envelope owned by the MCP server support boundary.
    """
    local_env = environment or load_local_environment()
    return success_envelope(
        command=MCP_HEALTH_TOOL,
        agent_owner=MCP_SERVER_OWNER,
        side_effect=SideEffect.READ_ONLY,
        data={
            "status": "ok",
            "environment": local_env.environment,
            "server_name": SERVER_NAME,
            "transport": local_env.transport,
            "schema_version": SCHEMA_VERSION,
            "tools": list(SUPPORT_TOOL_NAMES),
        },
    )


def build_config_envelope(environment: McpEnvironment | None = None) -> ToolEnvelope:
    """Build the read-only MCP server configuration envelope.

    Args:
        environment: Optional resolved local MCP environment.

    Returns:
        Successful configuration envelope owned by the MCP server support boundary.
    """
    local_env = environment or load_local_environment()
    tool_metadata = [
        {
            "name": MCP_HEALTH_TOOL,
            "agent_owner": MCP_SERVER_OWNER,
            "side_effect": SideEffect.READ_ONLY.value,
            "description": SUPPORT_TOOL_DESCRIPTIONS[MCP_HEALTH_TOOL],
        },
        {
            "name": MCP_CONFIG_TOOL,
            "agent_owner": MCP_SERVER_OWNER,
            "side_effect": SideEffect.READ_ONLY.value,
            "description": SUPPORT_TOOL_DESCRIPTIONS[MCP_CONFIG_TOOL],
        },
    ]
    return success_envelope(
        command=MCP_CONFIG_TOOL,
        agent_owner=MCP_SERVER_OWNER,
        side_effect=SideEffect.READ_ONLY,
        data={
            "environment": local_env.environment,
            "server_name": SERVER_NAME,
            "transport": local_env.transport,
            "artifact_root": str(local_env.artifact_root),
            "tool_count": len(tool_metadata),
            "tools": tool_metadata,
            "policy": local_env.policy_flags(),
            "safety": dict(UNREGISTERED_CAPABILITY_FLAGS),
        },
    )


def main() -> None:
    """Run the MCP server over stdio transport."""
    local_env = load_local_environment()
    create_server(local_env).run(transport=local_env.transport)


if __name__ == "__main__":
    main()
