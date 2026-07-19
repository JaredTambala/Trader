"""MCP registrations for Evaluation Agent tools."""

from __future__ import annotations

from collections.abc import Callable

from mcp.server.fastmcp import FastMCP
from mcp.types import CallToolResult

from trader_mcp.adapters import result_to_mcp_result
from trader_mcp.constants import (
    EVALUATION_GENERATE_PARAMETER_OPTIMIZATION_REPORT_TOOL,
    EVALUATION_TOOL_DESCRIPTIONS,
)
from trader_mcp.environment import McpEnvironment
from trader_research.foundation import ResearchArtifactStore
from trader_research.review import generate_parameter_optimization_report


ResearchArtifactStoreProvider = Callable[[], ResearchArtifactStore]


def register_evaluation_tools(
    server: FastMCP,
    environment: McpEnvironment,
    *,
    artifact_store_provider: ResearchArtifactStoreProvider | None = None,
) -> None:
    """Register untouched-holdout Evaluation tools."""
    del environment

    @server.tool(
        name=EVALUATION_GENERATE_PARAMETER_OPTIMIZATION_REPORT_TOOL,
        description=EVALUATION_TOOL_DESCRIPTIONS[EVALUATION_GENERATE_PARAMETER_OPTIMIZATION_REPORT_TOOL],
    )
    def evaluation_generate_parameter_optimization_report(
        optimization_run_ref: str,
        holdout_backtest_run_ref: str,
    ) -> CallToolResult:
        envelope = generate_parameter_optimization_report(
            optimization_run_ref=optimization_run_ref,
            holdout_backtest_run_ref=holdout_backtest_run_ref,
            artifact_store=artifact_store_provider() if artifact_store_provider is not None else None,
        )
        return CallToolResult(**result_to_mcp_result(envelope))
