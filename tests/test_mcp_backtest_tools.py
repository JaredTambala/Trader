from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import anyio

from tests.test_research_backtests import _config, _sample_store_and_reports, _validated_candidate
from trader_mcp.constants import (
    MCP_CONFIG_TOOL,
    REGISTERED_TOOL_NAMES,
    RESEARCH_COMPARE_BACKTEST_RESULTS_TOOL,
    RESEARCH_GET_BACKTEST_RESULTS_TOOL,
    RESEARCH_RUN_BACKTEST_TOOL,
)
from trader_mcp.environment import load_local_environment
from trader_mcp.server import create_server


def test_mcp_backtest_tools_are_registered_and_run_tool_is_gated(tmp_path: Path) -> None:
    environment = replace(
        load_local_environment("env.template"),
        artifact_root=tmp_path / "artifacts",
        allow_backtests=False,
    )
    server = create_server(environment)

    async def _run() -> None:
        tools = await server.list_tools()
        config = await server.call_tool(MCP_CONFIG_TOOL, {})
        result = await server.call_tool(RESEARCH_RUN_BACKTEST_TOOL, {})

        tool_names = {tool.name for tool in tools}
        assert tool_names == set(REGISTERED_TOOL_NAMES)
        assert RESEARCH_RUN_BACKTEST_TOOL in tool_names
        assert RESEARCH_GET_BACKTEST_RESULTS_TOOL in tool_names
        assert RESEARCH_COMPARE_BACKTEST_RESULTS_TOOL in tool_names
        config_tools = {tool["name"]: tool for tool in config.structuredContent["data"]["tools"]}
        assert config_tools[RESEARCH_RUN_BACKTEST_TOOL]["agent_owner"] == "Quant Research Supervisor Agent"
        assert config_tools[RESEARCH_RUN_BACKTEST_TOOL]["side_effect"] == "local_mutating"
        assert config_tools[RESEARCH_GET_BACKTEST_RESULTS_TOOL]["side_effect"] == "read_only"
        assert config_tools[RESEARCH_COMPARE_BACKTEST_RESULTS_TOOL]["side_effect"] == "local_mutating"
        assert config.structuredContent["data"]["safety"]["backtest_tools_registered"] is True
        assert config.structuredContent["data"]["safety"]["backtest_execution_allowed"] is False
        assert result.isError is True
        assert result.structuredContent["errors"][0]["code"] == "backtests_not_allowed"

    anyio.run(_run)


def test_mcp_backtest_run_and_lookup_flow_succeeds(tmp_path: Path) -> None:
    artifact_root = tmp_path / "artifacts"
    store, dataset_manifest, data_quality_report = _sample_store_and_reports(tmp_path)
    candidate, validation_report = _validated_candidate(artifact_root)
    environment = replace(
        load_local_environment("env.template"),
        artifact_root=artifact_root,
        allow_backtests=True,
    )
    server = create_server(
        environment,
        event_store_provider=lambda: store,
        backtest_config_provider=lambda: _config(tmp_path),
    )

    async def _run() -> None:
        config = await server.call_tool(MCP_CONFIG_TOOL, {})
        first_run = await server.call_tool(
            RESEARCH_RUN_BACKTEST_TOOL,
            {
                "strategy_candidate_manifest": candidate,
                "strategy_candidate_validation_report": validation_report,
                "dataset_manifest": dataset_manifest,
                "data_quality_report": data_quality_report,
                "max_runs": 4,
            },
        )
        second_run = await server.call_tool(
            RESEARCH_RUN_BACKTEST_TOOL,
            {
                "strategy_candidate_manifest": candidate,
                "strategy_candidate_validation_report": validation_report,
                "dataset_manifest": dataset_manifest,
                "data_quality_report": data_quality_report,
                "max_runs": 5,
            },
        )
        run_ref = second_run.structuredContent["data"]["backtest_run_ref"]
        first_ref = first_run.structuredContent["data"]["backtest_run_ref"]
        _update_metric_file(first_ref, sharpe=1.0)
        _update_metric_file(run_ref, sharpe=2.0)
        lookup = await server.call_tool(RESEARCH_GET_BACKTEST_RESULTS_TOOL, {"run_id": run_ref["run_id"]})
        comparison = await server.call_tool(
            RESEARCH_COMPARE_BACKTEST_RESULTS_TOOL,
            {
                "backtest_runs": [
                    {"backtest_run_ref": first_ref},
                    {"artifact_dir": run_ref["artifact_dir"]},
                ]
            },
        )

        assert config.structuredContent["data"]["safety"]["backtest_execution_allowed"] is True
        assert first_run.isError is False
        assert second_run.isError is False
        assert run_ref["dataset_id"] == dataset_manifest["dataset_id"]
        assert Path(run_ref["artifact_paths"]["backtest_run_ref"]).exists()
        assert lookup.isError is False
        assert lookup.structuredContent["data"]["summary"]["run_id"] == run_ref["run_id"]
        assert lookup.structuredContent["data"]["data_scope"]["dataset_id"] == dataset_manifest["dataset_id"]
        assert comparison.isError is False
        report = comparison.structuredContent["data"]["comparison_report"]
        assert report["best_run_id"] == run_ref["run_id"]
        assert Path(comparison.structuredContent["artifacts"]["comparison_report"]["path"]).exists()

    anyio.run(_run)


def _update_metric_file(run_ref: dict[str, object], **updates: float) -> None:
    import json

    metrics_path = Path(str(run_ref["artifact_paths"]["metrics"]))
    metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
    metrics.update(updates)
    metrics_path.write_text(json.dumps(metrics, indent=2, sort_keys=True), encoding="utf-8")
