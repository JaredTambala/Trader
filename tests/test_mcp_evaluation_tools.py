from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import anyio

from tests.test_performance_reports import _run_with_trade_evidence
from trader_mcp.constants import EVALUATION_GENERATE_PERFORMANCE_REPORT_TOOL, MCP_CONFIG_TOOL, REGISTERED_TOOL_NAMES
from trader_mcp.environment import load_local_environment
from trader_mcp.server import create_server


def test_mcp_evaluation_tool_is_registered_and_not_backtest_gated(tmp_path: Path) -> None:
    environment = replace(
        load_local_environment("env.template"),
        artifact_root=tmp_path / "artifacts",
        allow_backtests=False,
    )
    server = create_server(environment)

    async def _run() -> None:
        tools = await server.list_tools()
        config = await server.call_tool(MCP_CONFIG_TOOL, {})

        tool_names = {tool.name for tool in tools}
        assert tool_names == set(REGISTERED_TOOL_NAMES)
        assert EVALUATION_GENERATE_PERFORMANCE_REPORT_TOOL in tool_names
        config_tools = {tool["name"]: tool for tool in config.structuredContent["data"]["tools"]}
        evaluation_tool = config_tools[EVALUATION_GENERATE_PERFORMANCE_REPORT_TOOL]
        assert evaluation_tool["agent_owner"] == "Evaluation Agent"
        assert evaluation_tool["side_effect"] == "local_mutating"
        assert config.structuredContent["data"]["safety"]["evaluation_tools_registered"] is True
        assert config.structuredContent["data"]["safety"]["backtest_execution_allowed"] is False

    anyio.run(_run)


def test_mcp_generate_performance_report_flow_succeeds(tmp_path: Path) -> None:
    artifact_root = tmp_path / "artifacts"
    run_payload, quality_report = _run_with_trade_evidence(artifact_root)
    run_ref = run_payload["data"]["backtest_run_ref"]
    environment = replace(
        load_local_environment("env.template"),
        artifact_root=artifact_root,
        allow_backtests=False,
    )
    server = create_server(environment)

    async def _run() -> None:
        result = await server.call_tool(
            EVALUATION_GENERATE_PERFORMANCE_REPORT_TOOL,
            {
                "backtest_run_ref": run_ref,
                "data_quality_report": quality_report,
            },
        )

        assert result.isError is False
        assert result.structuredContent["agent_owner"] == "Evaluation Agent"
        assert result.structuredContent["side_effect"] == "local_mutating"
        report = result.structuredContent["data"]["evaluation_report"]
        assert report["status"] == "passed"
        assert report["run_id"] == run_ref["run_id"]
        assert Path(result.structuredContent["artifacts"]["evaluation_report"]["path"]).exists()

    anyio.run(_run)
