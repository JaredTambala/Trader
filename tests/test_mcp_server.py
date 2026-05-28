from __future__ import annotations

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
    MCP_CONFIG_TOOL,
    MCP_HEALTH_TOOL,
    MCP_SERVER_OWNER,
    REGISTERED_TOOL_NAMES,
)
from trader_mcp.environment import load_local_environment
from trader_mcp.server import create_server


def test_local_env_loads_portable_configuration() -> None:
    local_env = load_local_environment()

    assert local_env.environment == "local"
    assert local_env.transport == "stdio"
    assert str(local_env.artifact_root) == "artifacts/research"
    assert local_env.trader_config_path is None
    assert local_env.policy_flags() == {
        "allow_broker_mutation": False,
        "allow_raw_sql": False,
        "allow_data_loading": False,
        "allow_backtests": False,
    }


def test_create_server_registers_support_and_data_tools() -> None:
    local_env = load_local_environment()
    server = create_server(local_env)

    async def _run() -> None:
        tools = await server.list_tools()

        assert {tool.name for tool in tools} == set(REGISTERED_TOOL_NAMES)

    anyio.run(_run)


def test_health_tool_returns_read_only_mcp_server_envelope() -> None:
    local_env = load_local_environment()
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


def test_config_tool_excludes_broker_raw_sql_and_backtest_tools() -> None:
    local_env = load_local_environment()
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
        assert inventory_tool["agent_owner"] == "Data Agent"
        assert inventory_tool["side_effect"] == "read_only"
        assert quality_tool["side_effect"] == "read_only"
        assert ensure_tool["side_effect"] == "local_mutating"
        assert "research_run_backtest" not in tool_names
        assert data["policy"] == local_env.policy_flags()
        assert data["safety"] == {
            **CAPABILITY_REGISTRATION_FLAGS,
            "data_loading_mutation_allowed": local_env.allow_data_loading,
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
