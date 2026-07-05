from __future__ import annotations

from dataclasses import replace
from datetime import timedelta
import os
from pathlib import Path
import sys

import anyio
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.types import CallToolResult

from trader_mcp.constants import (
    CAPABILITY_REGISTRATION_FLAGS,
    DATA_ENSURE_LOADED_TOOL,
    DATA_GET_INVENTORY_TOOL,
    DATA_SUMMARIZE_QUALITY_TOOL,
    EVALUATION_GENERATE_PERFORMANCE_REPORT_TOOL,
    MCP_CONFIG_TOOL,
    MCP_HEALTH_TOOL,
    MCP_SERVER_OWNER,
    REGISTERED_TOOL_NAMES,
    RESEARCH_COMPARE_BACKTEST_RESULTS_TOOL,
    RESEARCH_CREATE_RISK_MANAGER_CANDIDATE_TOOL,
    RESEARCH_CREATE_STRATEGY_CANDIDATE_TOOL,
    RESEARCH_GET_BACKTEST_RESULTS_TOOL,
    RESEARCH_LIST_RISK_MANAGER_TEMPLATES_TOOL,
    RESEARCH_LIST_STRATEGY_TEMPLATES_TOOL,
    RESEARCH_RUN_BACKTEST_TOOL,
    RESEARCH_VALIDATE_STRATEGY_CANDIDATE_TOOL,
)
from trader_mcp.environment import load_local_environment
from trader_mcp.server import create_server


def test_local_env_loads_portable_configuration() -> None:
    local_env = load_local_environment("env.template")

    assert local_env.environment == "local"
    assert local_env.transport == "stdio"
    assert str(local_env.artifact_root) == "artifacts/research"
    assert local_env.trader_config_path is None
    assert local_env.policy_flags() == {
        "allow_broker_mutation": False,
        "allow_raw_sql": False,
        "allow_symbol_provider_discovery": False,
        "allow_data_loading": False,
        "allow_backtests": False,
    }


def test_create_server_registers_support_and_data_tools() -> None:
    local_env = load_local_environment("env.template")
    server = create_server(local_env)

    async def _run() -> None:
        tools = await server.list_tools()

        assert {tool.name for tool in tools} == set(REGISTERED_TOOL_NAMES)

    anyio.run(_run)


def test_create_server_defers_tool_runtime_config_errors(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("MISSING_MCP_TEST_PG_PORT", raising=False)
    trader_config = tmp_path / "bad_tool_runtime.yaml"
    trader_config.write_text(
        """
database:
  event_store: postgres
  pg:
    port: ${MISSING_MCP_TEST_PG_PORT}
""".strip(),
        encoding="utf-8",
    )
    local_env = replace(load_local_environment("env.template"), trader_config_path=trader_config)
    server = create_server(local_env)

    async def _run() -> None:
        tools = await server.list_tools()
        health = await server.call_tool(MCP_HEALTH_TOOL, {})
        data_result = await server.call_tool(
            DATA_GET_INVENTORY_TOOL,
            {
                "symbols": ["DEMO"],
                "asset_class": "stocks",
                "timeframe": "1Min",
                "start": "2026-01-20T12:00:00Z",
                "end": "2026-01-20T12:11:00Z",
            },
        )

        assert {tool.name for tool in tools} == set(REGISTERED_TOOL_NAMES)
        assert health.isError is False
        assert data_result.isError is True
        assert data_result.structuredContent is not None
        assert data_result.structuredContent["errors"][0]["code"] == "tool_runtime_configuration_error"
        assert data_result.structuredContent["data"]["trader_config_path"] == str(trader_config)

    anyio.run(_run)


def test_tool_runtime_env_file_is_used_for_trader_config(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("MCP_TEST_TOOL_PORT", raising=False)
    tool_env = tmp_path / "tool.env"
    tool_env.write_text("MCP_TEST_TOOL_PORT=5432\n", encoding="utf-8")
    trader_config = tmp_path / "tool_runtime.yaml"
    trader_config.write_text(
        """
database:
  event_store: noop
  pg:
    port: ${MCP_TEST_TOOL_PORT}
market_data:
  source: alpaca
  asset_class: stocks
""".strip(),
        encoding="utf-8",
    )
    local_env = replace(load_local_environment("env.template"), trader_config_path=trader_config, tool_env_path=tool_env)
    server = create_server(local_env)

    async def _run() -> None:
        config = await server.call_tool(MCP_CONFIG_TOOL, {})
        data_result = await server.call_tool(
            DATA_GET_INVENTORY_TOOL,
            {
                "symbols": ["DEMO"],
                "asset_class": "stocks",
                "timeframe": "1Min",
                "start": "2026-01-20T12:00:00Z",
                "end": "2026-01-20T12:11:00Z",
            },
        )

        assert config.structuredContent is not None
        assert config.structuredContent["data"]["tool_runtime"]["env_path"] == str(tool_env)
        assert data_result.isError is True
        assert data_result.structuredContent is not None
        assert data_result.structuredContent["errors"][0]["code"] == "event_store_connection_unavailable"

    anyio.run(_run)


def test_health_tool_returns_read_only_mcp_server_envelope() -> None:
    local_env = load_local_environment("env.template")
    server = create_server(local_env)

    async def _run() -> None:
        result = await server.call_tool(MCP_HEALTH_TOOL, {})

        assert isinstance(result, CallToolResult)
        assert result.isError is False
        assert result.structuredContent is not None
        assert result.structuredContent["ok"] is True
        assert result.structuredContent["agent_owner"] == MCP_SERVER_OWNER
        assert result.structuredContent["side_effect"] == "read_only"
        assert result.structuredContent["data"]["environment"] == local_env.environment

    anyio.run(_run)


def test_config_tool_excludes_broker_raw_sql_and_gates_backtest_execution() -> None:
    local_env = load_local_environment("env.template")
    server = create_server(local_env)

    async def _run() -> None:
        result = await server.call_tool(MCP_CONFIG_TOOL, {})

        assert result.structuredContent is not None
        data = result.structuredContent["data"]
        tool_names = {tool["name"] for tool in data["tools"]}
        assert tool_names == set(REGISTERED_TOOL_NAMES)
        inventory_tool = next(tool for tool in data["tools"] if tool["name"] == DATA_GET_INVENTORY_TOOL)
        quality_tool = next(tool for tool in data["tools"] if tool["name"] == DATA_SUMMARIZE_QUALITY_TOOL)
        ensure_tool = next(tool for tool in data["tools"] if tool["name"] == DATA_ENSURE_LOADED_TOOL)
        template_tool = next(tool for tool in data["tools"] if tool["name"] == RESEARCH_LIST_STRATEGY_TEMPLATES_TOOL)
        create_candidate_tool = next(
            tool for tool in data["tools"] if tool["name"] == RESEARCH_CREATE_STRATEGY_CANDIDATE_TOOL
        )
        validate_candidate_tool = next(
            tool for tool in data["tools"] if tool["name"] == RESEARCH_VALIDATE_STRATEGY_CANDIDATE_TOOL
        )
        run_backtest_tool = next(tool for tool in data["tools"] if tool["name"] == RESEARCH_RUN_BACKTEST_TOOL)
        get_backtest_tool = next(tool for tool in data["tools"] if tool["name"] == RESEARCH_GET_BACKTEST_RESULTS_TOOL)
        compare_tool = next(tool for tool in data["tools"] if tool["name"] == RESEARCH_COMPARE_BACKTEST_RESULTS_TOOL)
        risk_template_tool = next(
            tool for tool in data["tools"] if tool["name"] == RESEARCH_LIST_RISK_MANAGER_TEMPLATES_TOOL
        )
        create_risk_tool = next(
            tool for tool in data["tools"] if tool["name"] == RESEARCH_CREATE_RISK_MANAGER_CANDIDATE_TOOL
        )
        performance_tool = next(
            tool for tool in data["tools"] if tool["name"] == EVALUATION_GENERATE_PERFORMANCE_REPORT_TOOL
        )
        assert inventory_tool["agent_owner"] == "Data Agent"
        assert inventory_tool["side_effect"] == "read_only"
        assert quality_tool["side_effect"] == "read_only"
        assert ensure_tool["side_effect"] == "local_mutating"
        assert template_tool["agent_owner"] == "Quant Research Supervisor Agent"
        assert template_tool["side_effect"] == "read_only"
        assert create_candidate_tool["side_effect"] == "local_mutating"
        assert validate_candidate_tool["side_effect"] == "local_mutating"
        assert run_backtest_tool["agent_owner"] == "Quant Research Supervisor Agent"
        assert run_backtest_tool["side_effect"] == "local_mutating"
        assert get_backtest_tool["side_effect"] == "read_only"
        assert compare_tool["agent_owner"] == "Quant Research Supervisor Agent"
        assert compare_tool["side_effect"] == "local_mutating"
        assert risk_template_tool["agent_owner"] == "Quant Research Supervisor Agent"
        assert risk_template_tool["side_effect"] == "read_only"
        assert create_risk_tool["agent_owner"] == "Quant Research Supervisor Agent"
        assert create_risk_tool["side_effect"] == "local_mutating"
        assert performance_tool["agent_owner"] == "Evaluation Agent"
        assert performance_tool["side_effect"] == "local_mutating"
        assert data["policy"] == local_env.policy_flags()
        assert data["safety"] == {
            **CAPABILITY_REGISTRATION_FLAGS,
            "symbol_provider_discovery_allowed": local_env.allow_symbol_provider_discovery,
            "data_loading_mutation_allowed": local_env.allow_data_loading,
            "backtest_execution_allowed": local_env.allow_backtests,
        }

    anyio.run(_run)


def test_stdio_server_lists_and_calls_health_tool() -> None:
    async def _run() -> None:
        env = dict(os.environ)
        src_path = str(Path(__file__).resolve().parents[1] / "src")
        env["PYTHONPATH"] = f"{src_path}{os.pathsep}{env.get('PYTHONPATH', '')}"
        server_params = StdioServerParameters(
            command=sys.executable,
            args=["-m", "trader_mcp.server"],
            cwd=Path(__file__).resolve().parents[1],
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
                result = await session.call_tool(MCP_HEALTH_TOOL, {})

        assert {tool.name for tool in tools.tools} == set(REGISTERED_TOOL_NAMES)
        assert result.isError is False
        assert result.structuredContent is not None
        assert result.structuredContent["command"] == MCP_HEALTH_TOOL
        assert result.structuredContent["agent_owner"] == MCP_SERVER_OWNER

    anyio.run(_run)
