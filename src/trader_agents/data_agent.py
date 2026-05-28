"""Deterministic Data Agent LangGraph graphs."""

from __future__ import annotations

from typing import Any

from langgraph.graph import END, START, StateGraph

from trader_mcp.constants import DATA_GET_INVENTORY_TOOL

from .state import DataAgentState, graph_error, mapping_or_empty
from .tool_client import McpToolClient


DATA_AGENT_OWNER = "Data Agent"
"""Display name required on Data Agent-owned tool envelopes."""


def build_data_agent_inventory_graph(tool_client: McpToolClient) -> Any:
    """Build the deterministic Data Agent inventory graph.

    Args:
        tool_client: MCP client used by the graph to call allowed tools.

    Returns:
        Compiled LangGraph graph that can be invoked with `DataAgentState`.
    """

    async def call_inventory(state: DataAgentState) -> DataAgentState:
        """Call the Data Agent inventory MCP tool.

        Args:
            state: Current Data Agent state.

        Returns:
            State update containing the MCP result, envelope, manifest, and status.
        """
        if DATA_GET_INVENTORY_TOOL not in set(state.get("tool_allowlist", [])):
            return _failed_state(
                "tool_not_allowlisted",
                f"{DATA_GET_INVENTORY_TOOL} is not allowlisted for this Data Agent identity.",
            )
        request = mapping_or_empty(state.get("inventory_request"))
        if not request:
            return _failed_state("missing_inventory_request", "Data Agent inventory request is missing.")

        result = dict(await tool_client.call_tool(DATA_GET_INVENTORY_TOOL, request))
        envelope = mapping_or_empty(result.get("structuredContent"))
        if not envelope:
            return {
                "mcp_result": result,
                **_failed_state("missing_structured_content", "MCP result did not include structuredContent."),
            }

        if envelope.get("agent_owner") != DATA_AGENT_OWNER:
            return {
                "mcp_result": result,
                "tool_envelope": envelope,
                **_failed_state("unexpected_agent_owner", "MCP envelope was not owned by Data Agent."),
            }

        errors = list(envelope.get("errors") or [])
        warnings = list(envelope.get("warnings") or [])
        if result.get("isError") or envelope.get("ok") is not True:
            return {
                "mcp_result": result,
                "tool_envelope": envelope,
                "status": "failed",
                "warnings": warnings,
                "errors": errors,
                "called_tools": [DATA_GET_INVENTORY_TOOL],
            }

        manifest = mapping_or_empty(mapping_or_empty(envelope.get("data")).get("dataset_manifest"))
        return {
            "mcp_result": result,
            "tool_envelope": envelope,
            "dataset_manifest": manifest,
            "status": "completed",
            "warnings": warnings,
            "errors": errors,
            "called_tools": [DATA_GET_INVENTORY_TOOL],
        }

    graph = StateGraph(DataAgentState)
    graph.add_node("data_get_inventory", call_inventory)
    graph.add_edge(START, "data_get_inventory")
    graph.add_edge("data_get_inventory", END)
    return graph.compile()


def _failed_state(code: str, message: str) -> DataAgentState:
    """Build a failed Data Agent state update.

    Args:
        code: Stable machine-readable error code.
        message: Human-readable error message.

    Returns:
        State update with failed status and one structured error.
    """
    return {
        "status": "failed",
        "warnings": [],
        "errors": [graph_error(code, message)],
    }
