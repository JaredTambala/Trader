"""Integration tests for MCP server composition and process lifecycle.

Subject: Lazy runtime composition, health, configuration failure, and stdio operation.
Level: Adapter integration.
Collaborators: Real FastMCP server and subprocess transport with local temporary configuration.
Guarantees: Startup remains provider-optional, configuration is lazy, and stdio calls succeed.
Non-goals: Catalogue policy semantics, capability correctness, remote services, or agent clients.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import timedelta
import os
from pathlib import Path
import subprocess
import sys

import anyio
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.types import CallToolResult

from trader_mcp.catalogue.definitions import (
    DATA_GET_INVENTORY_TOOL,
    MCP_CONFIG_TOOL,
    MCP_HEALTH_TOOL,
    MCP_SERVER_OWNER,
    REGISTERED_TOOL_NAMES,
)
from trader_mcp.catalogue.policy import load_local_environment
from trader_mcp.runtime.server import create_server


def test_server_starts_without_optional_optuna_or_mlflow_packages() -> None:
    """Start server composition when optional research providers cannot be imported."""
    script = """
import builtins
from pathlib import Path

real_import = builtins.__import__

def guarded_import(name, *args, **kwargs):
    if name.split(".", 1)[0] in {"mlflow", "optuna"}:
        raise ModuleNotFoundError(name)
    return real_import(name, *args, **kwargs)

builtins.__import__ = guarded_import

from trader_mcp.catalogue.policy import McpEnvironment
from trader_mcp.runtime.server import create_server

environment = McpEnvironment(
    environment="test",
    transport="stdio",
    artifact_root=Path("artifacts/research"),
    trader_config_path=None,
    tool_env_path=None,
    allow_broker_mutation=False,
    allow_raw_sql=False,
    allow_symbol_provider_discovery=False,
    allow_data_loading=False,
    allow_backtests=False,
    embeddings_provider="deterministic",
    embeddings_model="test",
    embeddings_base_url="",
    embeddings_api_key="",
    embeddings_timeout_seconds=1.0,
    knowledge_store="unavailable",
)
assert create_server(environment) is not None
"""
    completed = subprocess.run(
        [sys.executable, "-c", script],
        check=False,
        capture_output=True,
        cwd=Path(__file__).resolve().parents[3],
        text=True,
    )

    assert completed.returncode == 0, completed.stderr


def test_create_server_defers_tool_runtime_config_errors(
    tmp_path: Path, monkeypatch
) -> None:
    """Defer invalid execution configuration until its affected tool is called."""
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
    local_env = replace(
        load_local_environment("env.template"), trader_config_path=trader_config
    )
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
        assert (
            data_result.structuredContent["errors"][0]["code"]
            == "tool_runtime_configuration_error"
        )
        assert data_result.structuredContent["data"]["trader_config_path"] == str(
            trader_config
        )

    anyio.run(_run)


def test_tool_runtime_env_file_is_used_for_trader_config(
    tmp_path: Path, monkeypatch
) -> None:
    """Load execution-plane environment values only when resolving tool configuration."""
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
    local_env = replace(
        load_local_environment("env.template"),
        trader_config_path=trader_config,
        tool_env_path=tool_env,
    )
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
        assert config.structuredContent["data"]["tool_runtime"]["env_path"] == str(
            tool_env
        )
        assert data_result.isError is True
        assert data_result.structuredContent is not None
        assert (
            data_result.structuredContent["errors"][0]["code"]
            == "event_store_connection_unavailable"
        )

    anyio.run(_run)


def test_health_tool_returns_read_only_mcp_server_envelope() -> None:
    """Return successful read-only health metadata from the composed server."""
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


def test_stdio_server_lists_and_calls_health_tool() -> None:
    """List tools and call health through a real stdio subprocess session."""
    async def _run() -> None:
        env = dict(os.environ)
        src_path = str(Path(__file__).resolve().parents[3] / "src")
        env["PYTHONPATH"] = f"{src_path}{os.pathsep}{env.get('PYTHONPATH', '')}"
        server_params = StdioServerParameters(
            command=sys.executable,
            args=["-m", "trader_mcp.runtime.server"],
            cwd=Path(__file__).resolve().parents[3],
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
