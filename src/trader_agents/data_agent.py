"""Deterministic Data Agent LangGraph graphs."""

from __future__ import annotations

from typing import Any

from langgraph.graph import END, START, StateGraph

from trader_mcp.constants import (
    DATA_DISCOVER_SYMBOLS_TOOL,
    DATA_ENSURE_LOADED_TOOL,
    DATA_GET_INVENTORY_TOOL,
    DATA_SUMMARIZE_QUALITY_TOOL,
)

from .data_agent_policy import call_data_agent_policy, route_after_data_agent_policy
from .llm_client import LlmClient, RuntimeConfiguredLlmClient
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

    async def call_symbol_discovery(state: DataAgentState) -> DataAgentState:
        """Run mandatory exact-symbol discovery before inventory."""
        return await _call_symbol_discovery(state=state, tool_client=tool_client)

    async def call_inventory(state: DataAgentState) -> DataAgentState:
        """Call the Data Agent inventory MCP tool.

        Args:
            state: Current Data Agent state.

        Returns:
            State update containing the MCP result, envelope, manifest, and status.
        """
        return await _call_data_agent_tool(
            state=state,
            tool_client=tool_client,
            tool_name=DATA_GET_INVENTORY_TOOL,
            request_key="inventory_request",
            data_key="dataset_manifest",
            output_keys=("dataset_manifest",),
        )

    graph = StateGraph(DataAgentState)
    graph.add_node("data_discover_symbols", call_symbol_discovery)
    graph.add_node("data_get_inventory", call_inventory)
    graph.add_edge(START, "data_discover_symbols")
    graph.add_conditional_edges(
        "data_discover_symbols",
        _route_after_tool,
        {"continue": "data_get_inventory", "failed": END},
    )
    graph.add_edge("data_get_inventory", END)
    return graph.compile()


def build_data_agent_symbol_discovery_graph(tool_client: McpToolClient) -> Any:
    """Build a deterministic Data Agent symbol discovery graph."""

    async def call_symbol_discovery(state: DataAgentState) -> DataAgentState:
        return await _call_symbol_discovery(state=state, tool_client=tool_client)

    graph = StateGraph(DataAgentState)
    graph.add_node("data_discover_symbols", call_symbol_discovery)
    graph.add_edge(START, "data_discover_symbols")
    graph.add_edge("data_discover_symbols", END)
    return graph.compile()


def build_data_agent_quality_graph(tool_client: McpToolClient) -> Any:
    """Build the deterministic Data Agent inventory-plus-quality graph.

    Args:
        tool_client: MCP client used by the graph to call allowed tools.

    Returns:
        Compiled LangGraph graph that calls inventory then quality.
    """

    async def call_symbol_discovery(state: DataAgentState) -> DataAgentState:
        """Run mandatory exact-symbol discovery before inventory and quality."""
        return await _call_symbol_discovery(state=state, tool_client=tool_client)

    async def call_inventory(state: DataAgentState) -> DataAgentState:
        """Call the Data Agent inventory MCP tool.

        Args:
            state: Current Data Agent state.

        Returns:
            State update containing the inventory envelope.
        """
        return await _call_data_agent_tool(
            state=state,
            tool_client=tool_client,
            tool_name=DATA_GET_INVENTORY_TOOL,
            request_key="inventory_request",
            data_key="dataset_manifest",
            output_keys=("dataset_manifest",),
        )

    async def call_quality(state: DataAgentState) -> DataAgentState:
        """Call the Data Agent quality MCP tool.

        Args:
            state: Current Data Agent state.

        Returns:
            State update containing the quality report.
        """
        return await _call_data_agent_tool(
            state=state,
            tool_client=tool_client,
            tool_name=DATA_SUMMARIZE_QUALITY_TOOL,
            request_key="quality_request",
            data_key="data_quality_report",
            output_keys=("quality_report",),
        )

    graph = StateGraph(DataAgentState)
    graph.add_node("data_discover_symbols", call_symbol_discovery)
    graph.add_node("data_get_inventory", call_inventory)
    graph.add_node("data_summarize_quality", call_quality)
    graph.add_edge(START, "data_discover_symbols")
    graph.add_conditional_edges(
        "data_discover_symbols",
        _route_after_tool,
        {"continue": "data_get_inventory", "failed": END},
    )
    graph.add_conditional_edges(
        "data_get_inventory",
        _route_after_tool,
        {"continue": "data_summarize_quality", "failed": END},
    )
    graph.add_edge("data_summarize_quality", END)
    return graph.compile()


def build_data_agent_workflow_graph(tool_client: McpToolClient) -> Any:
    """Build the full deterministic Data Agent data workflow graph.

    Args:
        tool_client: MCP client used by the graph to call allowed tools.

    Returns:
        Compiled graph that inventories, checks quality, ensures data, and
        checks quality again through MCP tools only.
    """

    async def call_symbol_discovery(state: DataAgentState) -> DataAgentState:
        """Run mandatory exact-symbol discovery before the full data workflow."""
        return await _call_symbol_discovery(state=state, tool_client=tool_client)

    async def call_inventory(state: DataAgentState) -> DataAgentState:
        """Call the Data Agent inventory MCP tool.

        Args:
            state: Current Data Agent state.

        Returns:
            State update containing the initial dataset manifest.
        """
        return await _call_data_agent_tool(
            state=state,
            tool_client=tool_client,
            tool_name=DATA_GET_INVENTORY_TOOL,
            request_key="inventory_request",
            data_key="dataset_manifest",
            output_keys=("dataset_manifest",),
        )

    async def call_initial_quality(state: DataAgentState) -> DataAgentState:
        """Call the first Data Agent quality MCP tool.

        Args:
            state: Current Data Agent state.

        Returns:
            State update containing the initial quality report.
        """
        return await _call_data_agent_tool(
            state=state,
            tool_client=tool_client,
            tool_name=DATA_SUMMARIZE_QUALITY_TOOL,
            request_key="quality_request",
            data_key="data_quality_report",
            output_keys=("initial_quality_report", "quality_report"),
        )

    async def call_ensure_loaded(state: DataAgentState) -> DataAgentState:
        """Call the Data Agent ensure-loaded MCP tool when policy allows it.

        Args:
            state: Current Data Agent state.

        Returns:
            State update containing the load result or policy failure.
        """
        return await _call_ensure_loaded_with_policy(state=state, tool_client=tool_client)

    async def call_final_quality(state: DataAgentState) -> DataAgentState:
        """Call the final Data Agent quality MCP tool.

        Args:
            state: Current Data Agent state.

        Returns:
            State update containing the final quality report.
        """
        return await _call_data_agent_tool(
            state=state,
            tool_client=tool_client,
            tool_name=DATA_SUMMARIZE_QUALITY_TOOL,
            request_key="quality_request",
            data_key="data_quality_report",
            output_keys=("final_quality_report", "quality_report"),
        )

    graph = StateGraph(DataAgentState)
    graph.add_node("data_discover_symbols", call_symbol_discovery)
    graph.add_node("data_get_inventory", call_inventory)
    graph.add_node("initial_data_summarize_quality", call_initial_quality)
    graph.add_node("data_ensure_loaded", call_ensure_loaded)
    graph.add_node("final_data_summarize_quality", call_final_quality)
    graph.add_edge(START, "data_discover_symbols")
    graph.add_conditional_edges(
        "data_discover_symbols",
        _route_after_tool,
        {"continue": "data_get_inventory", "failed": END},
    )
    graph.add_conditional_edges(
        "data_get_inventory",
        _route_after_tool,
        {"continue": "initial_data_summarize_quality", "failed": END},
    )
    graph.add_conditional_edges(
        "initial_data_summarize_quality",
        _route_after_tool,
        {"continue": "data_ensure_loaded", "failed": END},
    )
    graph.add_conditional_edges(
        "data_ensure_loaded",
        _route_after_tool,
        {"continue": "final_data_summarize_quality", "failed": END},
    )
    graph.add_edge("final_data_summarize_quality", END)
    return graph.compile()


def build_data_agent_llm_policy_graph(
    tool_client: McpToolClient,
    llm_client: LlmClient | None = None,
    *,
    max_policy_decisions: int = 8,
) -> Any:
    """Build a Data Agent graph controlled by a bounded LLM policy node.

    Args:
        tool_client: MCP client used by validated tool nodes.
        llm_client: Provider-neutral LLM client. If omitted, runtime
            `TRADER_AGENTS_LLM_*` environment configuration is used.
        max_policy_decisions: Loop budget for policy decisions.

    Returns:
        Compiled graph that lets an LLM propose typed Data Agent actions while
        deterministic routing validates every tool call.
    """
    selected_llm_client = llm_client or RuntimeConfiguredLlmClient()

    async def call_policy(state: DataAgentState) -> DataAgentState:
        """Ask the LLM policy for one typed, validated Data Agent action."""
        return await call_data_agent_policy(
            state=state,
            llm_client=selected_llm_client,
            max_decisions=max_policy_decisions,
        )

    async def call_symbol_discovery(state: DataAgentState) -> DataAgentState:
        """Run symbol discovery chosen by the policy router."""
        return await _call_symbol_discovery(state=state, tool_client=tool_client)

    async def call_inventory(state: DataAgentState) -> DataAgentState:
        """Run inventory chosen by the policy router."""
        return await _call_data_agent_tool(
            state=state,
            tool_client=tool_client,
            tool_name=DATA_GET_INVENTORY_TOOL,
            request_key="inventory_request",
            data_key="dataset_manifest",
            output_keys=("dataset_manifest",),
        )

    async def call_quality(state: DataAgentState) -> DataAgentState:
        """Run quality summarization chosen by the policy router."""
        return await _call_data_agent_tool(
            state=state,
            tool_client=tool_client,
            tool_name=DATA_SUMMARIZE_QUALITY_TOOL,
            request_key="quality_request",
            data_key="data_quality_report",
            output_keys=("quality_report",),
        )

    async def call_ensure_loaded(state: DataAgentState) -> DataAgentState:
        """Run ensure-loaded chosen by the policy router."""
        return await _call_ensure_loaded_with_policy(state=state, tool_client=tool_client)

    graph = StateGraph(DataAgentState)
    graph.add_node("data_agent_policy", call_policy)
    graph.add_node("data_discover_symbols", call_symbol_discovery)
    graph.add_node("data_get_inventory", call_inventory)
    graph.add_node("data_summarize_quality", call_quality)
    graph.add_node("data_ensure_loaded", call_ensure_loaded)
    graph.add_edge(START, "data_agent_policy")
    graph.add_conditional_edges(
        "data_agent_policy",
        route_after_data_agent_policy,
        {
            "data_discover_symbols": "data_discover_symbols",
            "data_get_inventory": "data_get_inventory",
            "data_summarize_quality": "data_summarize_quality",
            "data_ensure_loaded": "data_ensure_loaded",
            "data_agent_policy": "data_agent_policy",
            "done": END,
        },
    )
    for node_name in (
        "data_discover_symbols",
        "data_get_inventory",
        "data_summarize_quality",
        "data_ensure_loaded",
    ):
        graph.add_conditional_edges(
            node_name,
            _route_after_policy_tool,
            {"continue": "data_agent_policy", "failed": END},
        )
    return graph.compile()


async def _call_symbol_discovery(
    *,
    state: DataAgentState,
    tool_client: McpToolClient,
) -> DataAgentState:
    """Call mandatory symbol discovery and decide whether downstream tools may run."""
    update = await _call_data_agent_tool(
        state=state,
        tool_client=tool_client,
        tool_name=DATA_DISCOVER_SYMBOLS_TOOL,
        request_key="symbol_discovery_request",
        data_key="symbol_discovery_report",
        output_keys=("symbol_discovery_report",),
    )
    if update.get("status") == "failed":
        errors = list(update.get("errors", []))
        if errors and errors[0].get("code") == "provider_not_configured":
            return {
                **update,
                "status": "blocked",
                "blockers": [
                    {
                        "code": "provider_not_configured",
                        "message": errors[0].get("message", "Requested provider is not configured."),
                        "details": mapping_or_empty(update.get("last_tool_envelope")).get("data", {}),
                    }
                ],
                "errors": [],
            }
        return update

    report = mapping_or_empty(update.get("symbol_discovery_report"))
    propagated_requests = _requests_with_provider_context(state, report)
    if report.get("all_requested_symbols_exist") is False:
        return {
            **update,
            **propagated_requests,
            "status": "blocked",
            "blockers": [
                {
                    "code": "symbols_not_available",
                    "message": "Requested symbols are not available from the configured data source.",
                    "missing_symbols": list(report.get("missing_symbols") or []),
                    "resolved_provider": report.get("resolved_provider"),
                    "instrument_type": report.get("instrument_type"),
                    "bar_type": report.get("bar_type"),
                }
            ],
            "errors": [],
        }
    return {**update, **propagated_requests, "blockers": []}


async def _call_ensure_loaded_with_policy(
    *,
    state: DataAgentState,
    tool_client: McpToolClient,
) -> DataAgentState:
    """Call ensure-loaded only when the Data Agent runtime policy permits it."""
    policy = mapping_or_empty(state.get("policy"))
    if policy.get("allow_data_loading") is not True:
        return _failed_state(
            "data_loading_not_allowed",
            "Data Agent graph policy does not allow data loading.",
            called_tools=list(state.get("called_tools", [])),
            warnings=list(state.get("warnings", [])),
        )
    return await _call_data_agent_tool(
        state=state,
        tool_client=tool_client,
        tool_name=DATA_ENSURE_LOADED_TOOL,
        request_key="ensure_request",
        data_key="load_result",
        output_keys=("load_result",),
    )


async def _call_data_agent_tool(
    *,
    state: DataAgentState,
    tool_client: McpToolClient,
    tool_name: str,
    request_key: str,
    data_key: str,
    output_keys: tuple[str, ...],
) -> DataAgentState:
    """Call one Data Agent MCP tool and extract a payload into state.

    Args:
        state: Current Data Agent state.
        tool_client: MCP client used to call the tool.
        tool_name: MCP tool name to call.
        request_key: State key containing JSON-native tool arguments.
        data_key: Envelope data key to extract.
        output_keys: State keys that should receive the extracted payload.

    Returns:
        State update with result, envelope, extracted payload, warnings, errors,
        status, and ordered called tools.
    """
    called_tools = list(state.get("called_tools", []))
    warnings = list(state.get("warnings", []))
    if tool_name not in set(state.get("tool_allowlist", [])):
        return _failed_state(
            "tool_not_allowlisted",
            f"{tool_name} is not allowlisted for this Data Agent identity.",
            called_tools=called_tools,
            warnings=warnings,
        )
    request = mapping_or_empty(state.get(request_key))
    if not request:
        return _failed_state(
            f"missing_{request_key}",
            f"Data Agent {request_key} is missing.",
            called_tools=called_tools,
            warnings=warnings,
        )

    result = dict(await tool_client.call_tool(tool_name, request))
    called_tools.append(tool_name)
    envelope = mapping_or_empty(result.get("structuredContent"))
    if not envelope:
        return {
            "mcp_result": result,
            "last_mcp_result": result,
            **_failed_state(
                "missing_structured_content",
                "MCP result did not include structuredContent.",
                called_tools=called_tools,
                warnings=warnings,
            ),
        }

    if envelope.get("agent_owner") != DATA_AGENT_OWNER:
        return {
            "mcp_result": result,
            "last_mcp_result": result,
            "tool_envelope": envelope,
            "last_tool_envelope": envelope,
            **_failed_state(
                "unexpected_agent_owner",
                "MCP envelope was not owned by Data Agent.",
                called_tools=called_tools,
                warnings=warnings,
            ),
        }

    envelope_warnings = list(envelope.get("warnings") or [])
    envelope_errors = list(envelope.get("errors") or [])
    if result.get("isError") or envelope.get("ok") is not True:
        return {
            "mcp_result": result,
            "last_mcp_result": result,
            "tool_envelope": envelope,
            "last_tool_envelope": envelope,
            "status": "failed",
            "warnings": [*warnings, *envelope_warnings],
            "blockers": [],
            "errors": envelope_errors,
            "called_tools": called_tools,
        }

    payload = mapping_or_empty(mapping_or_empty(envelope.get("data")).get(data_key))
    update: DataAgentState = {
        "mcp_result": result,
        "last_mcp_result": result,
        "tool_envelope": envelope,
        "last_tool_envelope": envelope,
        "status": "completed",
        "warnings": [*warnings, *envelope_warnings],
        "blockers": [],
        "errors": [],
        "called_tools": called_tools,
    }
    for output_key in output_keys:
        update[output_key] = payload
    return update


def _route_after_tool(state: DataAgentState) -> str:
    """Route a graph edge after a tool node.

    Args:
        state: Current Data Agent state.

    Returns:
        `failed` when the prior tool failed, otherwise `continue`.
    """
    return "failed" if state.get("status") in {"failed", "blocked"} else "continue"


def _route_after_policy_tool(state: DataAgentState) -> str:
    """Route back to policy after a successful policy-selected tool."""
    return "failed" if state.get("status") in {"failed", "blocked"} else "continue"


def _requests_with_provider_context(state: DataAgentState, report: dict[str, Any]) -> DataAgentState:
    """Return downstream requests updated with resolved provider context."""
    if not report:
        return {}
    provider = report.get("resolved_provider")
    instrument_type = report.get("instrument_type")
    bar_type = report.get("bar_type")
    legacy_asset_class = report.get("legacy_asset_class")
    updates: DataAgentState = {}
    for state_key in ("inventory_request", "quality_request", "ensure_request"):
        request = mapping_or_empty(state.get(state_key))
        if not request:
            continue
        updated = dict(request)
        if provider is not None:
            updated["provider"] = provider
        if instrument_type is not None:
            updated["instrument_type"] = instrument_type
        if bar_type is not None:
            updated["bar_type"] = bar_type
        if legacy_asset_class is not None:
            updated["asset_class"] = legacy_asset_class
        updates[state_key] = updated
    return updates


def _failed_state(
    code: str,
    message: str,
    *,
    called_tools: list[str] | None = None,
    warnings: list[str] | None = None,
) -> DataAgentState:
    """Build a failed Data Agent state update.

    Args:
        code: Stable machine-readable error code.
        message: Human-readable error message.
        called_tools: Ordered tools already called by the graph.
        warnings: Warnings already accumulated by the graph.

    Returns:
        State update with failed status and one structured error.
    """
    return {
        "status": "failed",
        "warnings": list(warnings or []),
        "blockers": [],
        "errors": [graph_error(code, message)],
        "called_tools": list(called_tools or []),
    }
