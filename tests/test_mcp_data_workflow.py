from __future__ import annotations

from dataclasses import replace
from datetime import timedelta
import json
import os
from pathlib import Path
import sys
from typing import Any, Mapping

import anyio
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from tests.support.duckdb_store import DuckDBEventStore
from trader.data import EventStore
from trader.sample_data import load_sample_market_data_csv
from trader_mcp.constants import (
    DATA_ENSURE_LOADED_TOOL,
    DATA_GET_INVENTORY_TOOL,
    DATA_SUMMARIZE_QUALITY_TOOL,
    MCP_CONFIG_TOOL,
    MCP_HEALTH_TOOL,
    REGISTERED_TOOL_NAMES,
)
from trader_mcp.environment import load_local_environment
from trader_mcp.server import create_server
from trader_research.data import DataEnsureLoadedPolicy, DataEnsureLoadedRequest


SAMPLE_CSV = Path("examples/data/demo_stock_1min.csv")


def _data_args(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "symbols": ["DEMO"],
        "asset_class": "stocks",
        "timeframe": "1Min",
        "start": "2026-01-20T12:00:00Z",
        "end": "2026-01-20T12:11:00Z",
    }
    payload.update(overrides)
    return payload


def test_mcp_server_lists_full_data_workflow_tools(tmp_path: Path) -> None:
    store = DuckDBEventStore(str(tmp_path / "events.duckdb"))
    server = create_server(load_local_environment("env.template"), event_store_provider=lambda: store)

    async def _run() -> None:
        tools = await server.list_tools()

        assert {tool.name for tool in tools} == set(REGISTERED_TOOL_NAMES)
        assert DATA_GET_INVENTORY_TOOL in {tool.name for tool in tools}
        assert DATA_SUMMARIZE_QUALITY_TOOL in {tool.name for tool in tools}
        assert DATA_ENSURE_LOADED_TOOL in {tool.name for tool in tools}

    anyio.run(_run)


def test_mcp_quality_tool_returns_sample_report(tmp_path: Path) -> None:
    store = DuckDBEventStore(str(tmp_path / "events.duckdb"))
    load_sample_market_data_csv(store, SAMPLE_CSV)
    server = create_server(load_local_environment("env.template"), event_store_provider=lambda: store)

    async def _run() -> None:
        result = await server.call_tool(DATA_SUMMARIZE_QUALITY_TOOL, _data_args())

        assert result.isError is False
        assert result.structuredContent is not None
        assert result.structuredContent["agent_owner"] == "Data Agent"
        assert result.structuredContent["side_effect"] == "read_only"
        report = result.structuredContent["data"]["data_quality_report"]
        assert report["total_bars"] == 12
        assert report["missing_gap_count"] == 0
        assert report["complete"] is True

    anyio.run(_run)


def test_mcp_quality_tool_returns_validation_errors(tmp_path: Path) -> None:
    store = DuckDBEventStore(str(tmp_path / "events.duckdb"))
    server = create_server(load_local_environment("env.template"), event_store_provider=lambda: store)

    async def _run() -> None:
        bad_datetime = await server.call_tool(DATA_SUMMARIZE_QUALITY_TOOL, _data_args(start="not-a-date"))
        bad_timeframe = await server.call_tool(DATA_SUMMARIZE_QUALITY_TOOL, _data_args(timeframe="bad"))

        assert bad_datetime.isError is True
        assert bad_datetime.structuredContent is not None
        assert bad_datetime.structuredContent["errors"][0]["code"] == "validation_error"
        assert "start must be an ISO-8601 timestamp string" in bad_datetime.structuredContent["errors"][0]["message"]
        assert bad_timeframe.isError is True
        assert bad_timeframe.structuredContent is not None
        assert bad_timeframe.structuredContent["errors"][0]["code"] == "validation_error"
        assert "Invalid timeframe" in bad_timeframe.structuredContent["errors"][0]["message"]

    anyio.run(_run)


def test_mcp_default_environment_rejects_sample_loading(tmp_path: Path) -> None:
    store = DuckDBEventStore(str(tmp_path / "events.duckdb"))
    server = create_server(load_local_environment("env.template"), event_store_provider=lambda: store)

    async def _run() -> None:
        result = await server.call_tool(
            DATA_ENSURE_LOADED_TOOL,
            _data_args(mode="sample", dry_run=False),
        )

        assert result.isError is True
        assert result.structuredContent is not None
        assert result.structuredContent["side_effect"] == "local_mutating"
        assert result.structuredContent["errors"][0]["code"] == "data_loading_not_allowed"

    anyio.run(_run)


def test_mcp_explicit_policy_allows_sample_loading(tmp_path: Path) -> None:
    store = DuckDBEventStore(str(tmp_path / "events.duckdb"))
    environment = replace(load_local_environment("env.template"), allow_data_loading=True)
    server = create_server(environment, event_store_provider=lambda: store)

    async def _run() -> None:
        result = await server.call_tool(
            DATA_ENSURE_LOADED_TOOL,
            _data_args(mode="sample", dry_run=False),
        )

        assert result.isError is False
        assert result.structuredContent is not None
        load_result = result.structuredContent["data"]["load_result"]
        assert load_result["mode"] == "sample"
        assert load_result["rows_loaded"] == 12
        assert load_result["post_load_manifest"]["total_rows"] == 12

    anyio.run(_run)


def test_mcp_backfill_dry_run_plans_without_writing_rows(tmp_path: Path) -> None:
    store = DuckDBEventStore(str(tmp_path / "events.duckdb"))
    server = create_server(load_local_environment("env.template"), event_store_provider=lambda: store)

    async def _run() -> None:
        backfill = await server.call_tool(
            DATA_ENSURE_LOADED_TOOL,
            _data_args(mode="backfill", dry_run=True),
        )
        inventory = await server.call_tool(DATA_GET_INVENTORY_TOOL, _data_args())

        assert backfill.isError is False
        assert backfill.structuredContent is not None
        load_result = backfill.structuredContent["data"]["load_result"]
        assert load_result["status"] == "planned"
        assert load_result["backfill_plan"]["network_calls"] == 0
        assert load_result["backfill_plan"]["writes"] == 0
        assert inventory.structuredContent is not None
        assert inventory.structuredContent["data"]["dataset_manifest"]["total_rows"] == 0

    anyio.run(_run)


def test_mcp_backfill_non_dry_run_runs_through_injected_tool_policy(tmp_path: Path) -> None:
    store = DuckDBEventStore(str(tmp_path / "events.duckdb"))
    environment = replace(load_local_environment("env.template"), allow_data_loading=True)
    calls: list[DataEnsureLoadedRequest] = []

    def _runner(request: DataEnsureLoadedRequest, event_store: EventStore) -> Mapping[str, Any]:
        calls.append(request)
        rows_loaded = load_sample_market_data_csv(event_store, SAMPLE_CSV)
        return {"rows_written": rows_loaded, "rows_loaded": rows_loaded, "source": "test_runner"}

    server = create_server(
        environment,
        event_store_provider=lambda: store,
        data_loading_policy=DataEnsureLoadedPolicy(allow_data_loading=True, backfill_runner=_runner),
    )

    async def _run() -> None:
        result = await server.call_tool(
            DATA_ENSURE_LOADED_TOOL,
            _data_args(mode="backfill", dry_run=False),
        )

        assert result.isError is False
        assert result.structuredContent is not None
        load_result = result.structuredContent["data"]["load_result"]
        assert calls[0].symbols == ("DEMO",)
        assert load_result["mode"] == "backfill"
        assert load_result["status"] == "ran"
        assert load_result["rows_loaded"] == 12
        assert load_result["post_load_manifest"]["total_rows"] == 12
        assert load_result["post_load_quality_report"]["complete"] is True

    anyio.run(_run)


def test_mcp_ensure_loaded_returns_validation_errors(tmp_path: Path) -> None:
    store = DuckDBEventStore(str(tmp_path / "events.duckdb"))
    server = create_server(load_local_environment("env.template"), event_store_provider=lambda: store)

    async def _run() -> None:
        result = await server.call_tool(DATA_ENSURE_LOADED_TOOL, _data_args(mode="existing", symbols=[]))

        assert result.isError is True
        assert result.structuredContent is not None
        assert result.structuredContent["errors"][0]["code"] == "validation_error"
        assert "at least one symbol" in result.structuredContent["errors"][0]["message"]

    anyio.run(_run)


def test_mcp_config_safety_distinguishes_registration_and_runtime_permission() -> None:
    environment = load_local_environment("env.template")
    server = create_server(environment)

    async def _run() -> None:
        result = await server.call_tool(MCP_CONFIG_TOOL, {})

        assert result.structuredContent is not None
        data = result.structuredContent["data"]
        tool_names = {tool["name"] for tool in data["tools"]}
        assert DATA_SUMMARIZE_QUALITY_TOOL in tool_names
        assert DATA_ENSURE_LOADED_TOOL in tool_names
        ensure_tool = next(tool for tool in data["tools"] if tool["name"] == DATA_ENSURE_LOADED_TOOL)
        assert ensure_tool["agent_owner"] == "Data Agent"
        assert ensure_tool["side_effect"] == "local_mutating"
        assert data["safety"]["data_loading_tools_registered"] is True
        assert data["safety"]["data_loading_mutation_allowed"] is environment.allow_data_loading
        assert data["safety"]["broker_mutating_tools_registered"] is False
        assert data["safety"]["raw_sql_tools_registered"] is False
        assert data["safety"]["backtest_tools_registered"] is False
        assert "research_run_backtest" not in tool_names
        assert "raw_sql" not in tool_names

    anyio.run(_run)


def test_stdio_mcp_complete_data_workflow_evidence() -> None:
    async def _run() -> None:
        repo_root = Path(__file__).resolve().parents[1]
        env = dict(os.environ)
        src_path = str(repo_root / "src")
        env["PYTHONPATH"] = f"{repo_root}{os.pathsep}{src_path}{os.pathsep}{env.get('PYTHONPATH', '')}"
        env["TRADER_MCP_TRADER_CONFIG_PATH"] = ""
        env["TRADER_MCP_ALLOW_DATA_LOADING"] = "true"
        server_params = StdioServerParameters(
            command=sys.executable,
            args=["-m", "tests.support.mcp_sample_loading_server"],
            cwd=repo_root,
            env=env,
        )
        async with stdio_client(server_params) as (read_stream, write_stream):
            async with ClientSession(
                read_stream,
                write_stream,
                read_timeout_seconds=timedelta(seconds=10),
            ) as session:
                await session.initialize()
                tools = await session.list_tools()
                results = [
                    await session.call_tool(MCP_HEALTH_TOOL, {}),
                    await session.call_tool(MCP_CONFIG_TOOL, {}),
                    await session.call_tool(DATA_GET_INVENTORY_TOOL, _data_args()),
                    await session.call_tool(DATA_SUMMARIZE_QUALITY_TOOL, _data_args()),
                    await session.call_tool(
                        DATA_ENSURE_LOADED_TOOL,
                        _data_args(mode="sample", dry_run=False),
                    ),
                    await session.call_tool(DATA_SUMMARIZE_QUALITY_TOOL, _data_args()),
                ]

        assert {tool.name for tool in tools.tools} == set(REGISTERED_TOOL_NAMES)
        for result in results:
            assert result.structuredContent is not None
            assert json.loads(result.content[0].text) == result.structuredContent

        initial_inventory = results[2].structuredContent["data"]["dataset_manifest"]
        initial_quality = results[3].structuredContent["data"]["data_quality_report"]
        load_result = results[4].structuredContent["data"]["load_result"]
        final_quality = results[5].structuredContent["data"]["data_quality_report"]
        assert initial_inventory["total_rows"] == 0
        assert initial_quality["complete"] is False
        assert load_result["mode"] == "sample"
        assert load_result["post_load_manifest"]["total_rows"] == 12
        assert final_quality["complete"] is True
        assert final_quality["total_bars"] == 12

    anyio.run(_run)
