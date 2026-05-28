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
    MCP_CONFIG_TOOL,
    MCP_HEALTH_TOOL,
    MCP_SERVER_OWNER,
    SUPPORT_TOOL_NAMES,
    UNREGISTERED_CAPABILITY_FLAGS,
)
from trader_mcp.environment import load_local_environment
from trader_mcp.server import create_server


def test_local_env_loads_portable_configuration() -> None:
    local_env = load_local_environment()

    assert local_env.environment == "local"
    assert local_env.transport == "stdio"
    assert str(local_env.artifact_root) == "artifacts/research"
    assert local_env.policy_flags() == {
        "allow_broker_mutation": False,
        "allow_raw_sql": False,
        "allow_data_loading": False,
        "allow_backtests": False,
    }


def test_create_server_registers_only_support_tools() -> None:
    local_env = load_local_environment()
    server = create_server(local_env)

    async def _run() -> None:
        tools = await server.list_tools()

        assert {tool.name for tool in tools} == set(SUPPORT_TOOL_NAMES)

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


def test_config_tool_excludes_research_and_mutating_tools() -> None:
    local_env = load_local_environment()
    server = create_server(local_env)

    async def _run() -> None:
        result = await server.call_tool(MCP_CONFIG_TOOL, {})

        assert result.structuredContent is not None
        data = result.structuredContent["data"]
        tool_names = {tool["name"] for tool in data["tools"]}
        assert tool_names == set(SUPPORT_TOOL_NAMES)
        assert "data_get_inventory" not in tool_names
        assert "research_run_backtest" not in tool_names
        assert data["policy"] == local_env.policy_flags()
        assert data["safety"] == UNREGISTERED_CAPABILITY_FLAGS

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

        assert {tool.name for tool in tools.tools} == set(SUPPORT_TOOL_NAMES)
        assert result.isError is False
        assert result.structuredContent is not None
        assert result.structuredContent["command"] == MCP_HEALTH_TOOL
        assert result.structuredContent["agent_owner"] == MCP_SERVER_OWNER

    anyio.run(_run)
