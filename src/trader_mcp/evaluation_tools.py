"""MCP registrations for Evaluation Agent tools."""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP
from mcp.types import CallToolResult

from trader_mcp.adapters import envelope_to_mcp_result
from trader_mcp.constants import EVALUATION_GENERATE_PERFORMANCE_REPORT_TOOL, EVALUATION_TOOL_DESCRIPTIONS
from trader_mcp.environment import McpEnvironment
from trader_research.evaluation import generate_performance_report as generate_performance_report_service


def register_evaluation_tools(server: FastMCP, environment: McpEnvironment) -> None:
    """Register Evaluation Agent tools on an MCP server."""

    @server.tool(
        name=EVALUATION_GENERATE_PERFORMANCE_REPORT_TOOL,
        description=EVALUATION_TOOL_DESCRIPTIONS[EVALUATION_GENERATE_PERFORMANCE_REPORT_TOOL],
    )
    def evaluation_generate_performance_report(
        run_id: str | None = None,
        artifact_dir: str | None = None,
        backtest_run_ref: dict[str, Any] | None = None,
        data_quality_report: dict[str, Any] | None = None,
        data_quality_report_path: str | None = None,
        data_quality_report_ref: dict[str, Any] | None = None,
    ) -> CallToolResult:
        """Generate one performance report from a persisted backtest bundle."""
        envelope = generate_performance_report_service(
            artifact_root=environment.artifact_root,
            run_id=run_id,
            artifact_dir=artifact_dir,
            backtest_run_ref=backtest_run_ref,
            data_quality_report=data_quality_report,
            data_quality_report_path=data_quality_report_path,
            data_quality_report_ref=data_quality_report_ref,
        )
        return CallToolResult(**envelope_to_mcp_result(envelope))
