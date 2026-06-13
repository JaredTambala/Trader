from __future__ import annotations

import os
from pathlib import Path
import sys
from typing import Any, Mapping

import anyio

from trader_mcp.constants import DATA_DISCOVER_SYMBOLS_TOOL, DATA_GET_INVENTORY_TOOL
from trader_agents.data_agent import build_data_agent_inventory_graph
from trader_agents.state import build_data_agent_initial_state
from trader_agents.tool_client import StdioMcpToolClient


def _inventory_state() -> dict[str, Any]:
    return build_data_agent_initial_state(
        symbols=("DEMO",),
        asset_class="stocks",
        timeframe="1Min",
        start="2026-01-20T12:00:00Z",
        end="2026-01-20T12:11:00Z",
    )


def _success_result(command: str, data_key: str, payload: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "content": [{"type": "text", "text": "{}"}],
        "structuredContent": {
            "ok": True,
            "command": command,
            "agent_owner": "Data Agent",
            "side_effect": "read_only",
            "data": {data_key: dict(payload)},
            "warnings": [],
            "errors": [],
        },
        "isError": False,
    }


def _discovery_report(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "all_requested_symbols_exist": True,
        "missing_symbols": [],
        "resolved_provider": "alpaca",
        "instrument_type": "stock",
        "bar_type": "trade_bar",
        "legacy_asset_class": "stocks",
    }
    payload.update(overrides)
    return payload


class SequenceMcpToolClient:
    def __init__(self, results: list[Mapping[str, Any]]) -> None:
        self._results = [dict(result) for result in results]
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def call_tool(self, tool_name: str, arguments: Mapping[str, Any]) -> Mapping[str, Any]:
        self.calls.append((tool_name, dict(arguments)))
        return self._results.pop(0)


class FailingIfCalledClient:
    async def call_tool(self, tool_name: str, arguments: Mapping[str, Any]) -> Mapping[str, Any]:
        raise AssertionError(f"unexpected tool call: {tool_name}")


def test_data_agent_initial_state_contains_identity_and_allowlist() -> None:
    state = _inventory_state()

    assert state["identity"]["agent_key"] == "data_agent"
    assert state["identity"]["display_name"] == "Data Agent"
    assert DATA_GET_INVENTORY_TOOL in state["tool_allowlist"]
    assert state["status"] == "ready"
    assert state["inventory_request"]["symbols"] == ["DEMO"]


def test_data_agent_graph_refuses_non_allowlisted_inventory_tool() -> None:
    state = _inventory_state()
    state["tool_allowlist"] = ["mcp_health", "mcp_get_config"]
    graph = build_data_agent_inventory_graph(FailingIfCalledClient())

    async def _run() -> None:
        output = await graph.ainvoke(state)

        assert output["status"] == "failed"
        assert output["errors"] == [
            {
                "code": "tool_not_allowlisted",
                "message": "data_discover_symbols is not allowlisted for this Data Agent identity.",
            }
        ]
        assert output["called_tools"] == []

    anyio.run(_run)


def test_data_agent_graph_preserves_failed_mcp_envelope() -> None:
    result = {
        "content": [{"type": "text", "text": "{}"}],
        "structuredContent": {
            "ok": False,
            "command": DATA_GET_INVENTORY_TOOL,
            "agent_owner": "Data Agent",
            "side_effect": "read_only",
            "data": {},
            "warnings": [],
            "errors": [{"code": "missing_data", "message": "No bars found."}],
        },
        "isError": True,
    }
    client = SequenceMcpToolClient(
        [
            _success_result(DATA_DISCOVER_SYMBOLS_TOOL, "symbol_discovery_report", _discovery_report()),
            result,
        ]
    )
    graph = build_data_agent_inventory_graph(client)

    async def _run() -> None:
        output = await graph.ainvoke(_inventory_state())

        assert output["status"] == "failed"
        assert output["tool_envelope"]["ok"] is False
        assert output["errors"] == [{"code": "missing_data", "message": "No bars found."}]
        assert output["called_tools"] == [DATA_DISCOVER_SYMBOLS_TOOL, DATA_GET_INVENTORY_TOOL]
        assert client.calls[0][0] == DATA_DISCOVER_SYMBOLS_TOOL
        assert client.calls[1][0] == DATA_GET_INVENTORY_TOOL

    anyio.run(_run)


def test_data_agent_graph_calls_inventory_through_stdio_mcp() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    env = dict(os.environ)
    env["PYTHONPATH"] = f"{repo_root}{os.pathsep}{repo_root / 'src'}{os.pathsep}{env.get('PYTHONPATH', '')}"
    env["TRADER_MCP_TRADER_CONFIG_PATH"] = ""
    client = StdioMcpToolClient(
        command=sys.executable,
        args=["-m", "tests.support.mcp_sample_inventory_server"],
        cwd=repo_root,
        env=env,
        read_timeout_seconds=10,
    )
    graph = build_data_agent_inventory_graph(client)

    async def _run() -> None:
        output = await graph.ainvoke(_inventory_state())

        assert output["status"] == "completed"
        assert output["tool_envelope"]["agent_owner"] == "Data Agent"
        assert output["tool_envelope"]["side_effect"] == "read_only"
        assert output["dataset_manifest"]["symbols"] == ["DEMO"]
        assert output["dataset_manifest"]["total_rows"] == 12
        assert output["dataset_manifest"]["symbols_detail"][0]["sources"] == {"sample": 12}
        assert output["called_tools"] == [DATA_DISCOVER_SYMBOLS_TOOL, DATA_GET_INVENTORY_TOOL]

    anyio.run(_run)


def test_trader_agents_do_not_import_platform_or_mcp_server_boundaries() -> None:
    forbidden = (
        "trader.data",
        "trader.market_data_queries",
        "trader_research.data",
        "trader_mcp.server",
    )
    offenders: list[str] = []
    for path in Path("src/trader_agents").rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        for snippet in forbidden:
            if snippet in text:
                offenders.append(f"{path}: contains {snippet!r}")

    assert offenders == []
