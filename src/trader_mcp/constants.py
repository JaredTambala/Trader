"""Static names and identifiers for the MCP research server."""

from __future__ import annotations

from typing import Final


SERVER_NAME: Final = "trader-research-mcp"
"""Name advertised by the MCP server."""

MCP_SERVER_OWNER: Final = "MCP Server"
"""Agent-owner label for MCP support tools."""

MCP_HEALTH_TOOL: Final = "mcp_health"
"""Tool name for MCP server health."""

MCP_CONFIG_TOOL: Final = "mcp_get_config"
"""Tool name for MCP server configuration."""

DATA_GET_INVENTORY_TOOL: Final = "data_get_inventory"
"""Tool name for read-only Data Agent inventory."""

DATA_SUMMARIZE_QUALITY_TOOL: Final = "data_summarize_quality"
"""Tool name for read-only Data Agent data-quality summaries."""

DATA_ENSURE_LOADED_TOOL: Final = "data_ensure_loaded"
"""Tool name for explicit Data Agent data inspection/loading."""

SUPPORT_TOOL_NAMES: Final = (MCP_HEALTH_TOOL, MCP_CONFIG_TOOL)
"""Read-only support tool names exposed by the MCP server."""

DATA_TOOL_NAMES: Final = (
    DATA_GET_INVENTORY_TOOL,
    DATA_SUMMARIZE_QUALITY_TOOL,
    DATA_ENSURE_LOADED_TOOL,
)
"""Data Agent tool names exposed by the MCP server."""

REGISTERED_TOOL_NAMES: Final = (*SUPPORT_TOOL_NAMES, *DATA_TOOL_NAMES)
"""All tool names currently exposed by the MCP server."""

SUPPORT_TOOL_DESCRIPTIONS: Final = {
    MCP_HEALTH_TOOL: "Return MCP server health and envelope metadata.",
    MCP_CONFIG_TOOL: "Return current MCP server safety and tool configuration.",
}
"""Descriptions for read-only support tools exposed by the MCP server."""

DATA_TOOL_DESCRIPTIONS: Final = {
    DATA_GET_INVENTORY_TOOL: "Return bounded market-data inventory and dataset manifest.",
    DATA_SUMMARIZE_QUALITY_TOOL: "Return bounded market-data quality gaps and completeness.",
    DATA_ENSURE_LOADED_TOOL: "Inspect, sample-load, or plan bounded market-data loading.",
}
"""Descriptions for Data Agent tools exposed by the MCP server."""

CAPABILITY_REGISTRATION_FLAGS: Final = {
    "broker_mutating_tools_registered": False,
    "raw_sql_tools_registered": False,
    "data_loading_tools_registered": True,
    "backtest_tools_registered": False,
}
"""Safety flags for registered and intentionally unregistered tool families."""

UNREGISTERED_CAPABILITY_FLAGS: Final = {
    "broker_mutating_tools_registered": False,
    "raw_sql_tools_registered": False,
    "data_loading_tools_registered": False,
    "backtest_tools_registered": False,
}
"""Historical pre-loading safety flags retained for older tests and docs."""
