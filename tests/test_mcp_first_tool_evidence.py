from __future__ import annotations

from datetime import timedelta
import json
import os
from pathlib import Path
import sys

import anyio
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from trader_mcp.constants import DATA_GET_INVENTORY_TOOL, REGISTERED_TOOL_NAMES


def test_stdio_client_calls_data_inventory_and_receives_data_agent_envelope() -> None:
    async def _run() -> None:
        repo_root = Path(__file__).resolve().parents[1]
        env = dict(os.environ)
        src_path = str(repo_root / "src")
        env["PYTHONPATH"] = f"{repo_root}{os.pathsep}{src_path}{os.pathsep}{env.get('PYTHONPATH', '')}"
        env["TRADER_MCP_TRADER_CONFIG_PATH"] = ""
        server_params = StdioServerParameters(
            command=sys.executable,
            args=["-m", "tests.support.mcp_sample_inventory_server"],
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
                result = await session.call_tool(
                    DATA_GET_INVENTORY_TOOL,
                    {
                        "symbols": ["DEMO"],
                        "asset_class": "stocks",
                        "timeframe": "1Min",
                        "start": "2026-01-20T12:00:00Z",
                        "end": "2026-01-20T12:11:00Z",
                    },
                )

        assert {tool.name for tool in tools.tools} == set(REGISTERED_TOOL_NAMES)
        assert result.isError is False
        assert result.structuredContent is not None
        assert result.structuredContent["ok"] is True
        assert result.structuredContent["command"] == DATA_GET_INVENTORY_TOOL
        assert result.structuredContent["agent_owner"] == "Data Agent"
        assert result.structuredContent["side_effect"] == "read_only"
        manifest = result.structuredContent["data"]["dataset_manifest"]
        assert manifest["symbols"] == ["DEMO"]
        assert manifest["total_rows"] == 12
        assert manifest["complete"] is True
        assert manifest["symbols_detail"][0]["sources"] == {"sample": 12}
        assert json.loads(result.content[0].text) == result.structuredContent

    anyio.run(_run)
