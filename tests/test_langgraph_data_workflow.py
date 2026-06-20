from __future__ import annotations

import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from typing import Any, Mapping

import anyio

from trader_mcp.constants import (
    DATA_DISCOVER_SYMBOLS_TOOL,
    DATA_ENSURE_LOADED_TOOL,
    DATA_GET_INVENTORY_TOOL,
    DATA_SUMMARIZE_QUALITY_TOOL,
)
from trader_agents.data_agent import build_data_agent_quality_graph, build_data_agent_workflow_graph
from trader_agents.state import build_data_agent_initial_state
from trader_agents.tool_client import PersistentStdioMcpToolClient, StdioMcpToolClient


def _state(**overrides: object) -> dict[str, Any]:
    payload = {
        "symbols": ("DEMO",),
        "asset_class": "stocks",
        "timeframe": "1Min",
        "start": "2026-01-20T12:00:00Z",
        "end": "2026-01-20T12:11:00Z",
    }
    payload.update(overrides)
    return build_data_agent_initial_state(**payload)


def _success_result(command: str, data_key: str, payload: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "content": [{"type": "text", "text": "{}"}],
        "structuredContent": {
            "ok": True,
            "command": command,
            "agent_owner": "Data Agent",
            "side_effect": "local_mutating" if command == DATA_ENSURE_LOADED_TOOL else "read_only",
            "data": {data_key: dict(payload)},
            "warnings": [],
            "errors": [],
        },
        "isError": False,
    }


def _discovery_result(**overrides: object) -> dict[str, Any]:
    payload: dict[str, object] = {
        "all_requested_symbols_exist": True,
        "missing_symbols": [],
        "resolved_provider": "alpaca",
        "instrument_type": "stock",
        "bar_type": "trade_bar",
        "legacy_asset_class": "stocks",
    }
    payload.update(overrides)
    return _success_result(DATA_DISCOVER_SYMBOLS_TOOL, "symbol_discovery_report", payload)


def _error_result(command: str, code: str = "validation_error") -> dict[str, Any]:
    return {
        "content": [{"type": "text", "text": "{}"}],
        "structuredContent": {
            "ok": False,
            "command": command,
            "agent_owner": "Data Agent",
            "side_effect": "read_only",
            "data": {},
            "warnings": [],
            "errors": [{"code": code, "message": "Quality failed."}],
        },
        "isError": True,
    }


def _provider_mismatch_result() -> dict[str, Any]:
    return {
        "content": [{"type": "text", "text": "{}"}],
        "structuredContent": {
            "ok": False,
            "command": DATA_DISCOVER_SYMBOLS_TOOL,
            "agent_owner": "Data Agent",
            "side_effect": "read_only",
            "data": {
                "requested_provider": "polygon",
                "configured_provider": "alpaca",
                "resolved_provider": None,
                "provider_match": False,
            },
            "warnings": [],
            "errors": [{"code": "provider_not_configured", "message": "Provider mismatch."}],
        },
        "isError": True,
    }


class SequenceMcpToolClient:
    def __init__(self, results: list[Mapping[str, Any]]) -> None:
        self._results = [dict(result) for result in results]
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def call_tool(self, tool_name: str, arguments: Mapping[str, Any]) -> Mapping[str, Any]:
        self.calls.append((tool_name, dict(arguments)))
        return self._results.pop(0)


def test_data_agent_quality_graph_blocks_missing_symbols_before_inventory() -> None:
    client = SequenceMcpToolClient(
        [
            _discovery_result(
                all_requested_symbols_exist=False,
                missing_symbols=["MISSING"],
            )
        ]
    )
    graph = build_data_agent_quality_graph(client)

    async def _run() -> None:
        output = await graph.ainvoke(_state(symbols=("MISSING",)))

        assert output["status"] == "blocked"
        assert output["blockers"][0]["code"] == "symbols_not_available"
        assert output["blockers"][0]["missing_symbols"] == ["MISSING"]
        assert output["called_tools"] == [DATA_DISCOVER_SYMBOLS_TOOL]
        assert [call[0] for call in client.calls] == [DATA_DISCOVER_SYMBOLS_TOOL]

    anyio.run(_run)


def test_data_agent_quality_graph_blocks_provider_mismatch_before_inventory() -> None:
    client = SequenceMcpToolClient([_provider_mismatch_result()])
    graph = build_data_agent_quality_graph(client)

    async def _run() -> None:
        output = await graph.ainvoke(_state(provider="polygon"))

        assert output["status"] == "blocked"
        assert output["blockers"][0]["code"] == "provider_not_configured"
        assert output["called_tools"] == [DATA_DISCOVER_SYMBOLS_TOOL]
        assert [call[0] for call in client.calls] == [DATA_DISCOVER_SYMBOLS_TOOL]

    anyio.run(_run)


def test_data_agent_quality_graph_succeeds_against_stdio_sample_server() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    env = dict(os.environ)
    src_path = str(repo_root / "src")
    env["PYTHONPATH"] = f"{repo_root}{os.pathsep}{src_path}{os.pathsep}{env.get('PYTHONPATH', '')}"
    env["TRADER_MCP_TRADER_CONFIG_PATH"] = ""
    client = StdioMcpToolClient(
        command=sys.executable,
        args=["-m", "tests.support.mcp_sample_inventory_server"],
        cwd=repo_root,
        env=env,
        read_timeout_seconds=10,
    )
    graph = build_data_agent_quality_graph(client)

    async def _run() -> None:
        output = await graph.ainvoke(_state())

        assert output["status"] == "completed"
        assert output["dataset_manifest"]["total_rows"] == 12
        assert output["quality_report"]["total_bars"] == 12
        assert output["quality_report"]["complete"] is True
        assert output["called_tools"] == [
            DATA_DISCOVER_SYMBOLS_TOOL,
            DATA_GET_INVENTORY_TOOL,
            DATA_SUMMARIZE_QUALITY_TOOL,
        ]

    anyio.run(_run)


def test_data_agent_quality_graph_refuses_removed_quality_allowlist() -> None:
    client = SequenceMcpToolClient(
        [
            _discovery_result(),
            _success_result(DATA_GET_INVENTORY_TOOL, "dataset_manifest", {"symbols": ["DEMO"]}),
        ]
    )
    state = _state()
    state["tool_allowlist"] = [DATA_DISCOVER_SYMBOLS_TOOL, DATA_GET_INVENTORY_TOOL]
    graph = build_data_agent_quality_graph(client)

    async def _run() -> None:
        output = await graph.ainvoke(state)

        assert output["status"] == "failed"
        assert output["errors"][0]["code"] == "tool_not_allowlisted"
        assert output["called_tools"] == [DATA_DISCOVER_SYMBOLS_TOOL, DATA_GET_INVENTORY_TOOL]
        assert [call[0] for call in client.calls] == [DATA_DISCOVER_SYMBOLS_TOOL, DATA_GET_INVENTORY_TOOL]

    anyio.run(_run)


def test_data_agent_quality_graph_preserves_failed_quality_envelope() -> None:
    client = SequenceMcpToolClient(
        [
            _discovery_result(),
            _success_result(DATA_GET_INVENTORY_TOOL, "dataset_manifest", {"symbols": ["DEMO"]}),
            _error_result(DATA_SUMMARIZE_QUALITY_TOOL, code="validation_error"),
        ]
    )
    graph = build_data_agent_quality_graph(client)

    async def _run() -> None:
        output = await graph.ainvoke(_state())

        assert output["status"] == "failed"
        assert output["tool_envelope"]["ok"] is False
        assert output["errors"] == [{"code": "validation_error", "message": "Quality failed."}]
        assert output["called_tools"] == [
            DATA_DISCOVER_SYMBOLS_TOOL,
            DATA_GET_INVENTORY_TOOL,
            DATA_SUMMARIZE_QUALITY_TOOL,
        ]

    anyio.run(_run)


def test_data_agent_workflow_refuses_loading_when_policy_disallows_mutation() -> None:
    client = SequenceMcpToolClient(
        [
            _discovery_result(),
            _success_result(DATA_GET_INVENTORY_TOOL, "dataset_manifest", {"symbols": ["DEMO"]}),
            _success_result(
                DATA_SUMMARIZE_QUALITY_TOOL,
                "data_quality_report",
                {"complete": False, "total_bars": 0},
            ),
        ]
    )
    graph = build_data_agent_workflow_graph(client)

    async def _run() -> None:
        output = await graph.ainvoke(_state(load_mode="sample", allow_data_loading=False))

        assert output["status"] == "failed"
        assert output["errors"][0]["code"] == "data_loading_not_allowed"
        assert output["called_tools"] == [
            DATA_DISCOVER_SYMBOLS_TOOL,
            DATA_GET_INVENTORY_TOOL,
            DATA_SUMMARIZE_QUALITY_TOOL,
        ]
        assert [call[0] for call in client.calls] == [
            DATA_DISCOVER_SYMBOLS_TOOL,
            DATA_GET_INVENTORY_TOOL,
            DATA_SUMMARIZE_QUALITY_TOOL,
        ]

    anyio.run(_run)


def test_data_agent_workflow_succeeds_with_sample_loading_through_mcp_client() -> None:
    async def _run() -> None:
        repo_root = Path(__file__).resolve().parents[1]
        env = dict(os.environ)
        src_path = str(repo_root / "src")
        env["PYTHONPATH"] = f"{repo_root}{os.pathsep}{src_path}{os.pathsep}{env.get('PYTHONPATH', '')}"
        env["TRADER_MCP_ALLOW_DATA_LOADING"] = "true"
        with TemporaryDirectory(prefix="trader-data-agent-config-") as tmp_dir:
            config_path = Path(tmp_dir) / "configured_universe.yaml"
            config_path.write_text(
                """
market_data:
  source: alpaca
  asset_class: stocks
  symbols: [DEMO]
""".strip(),
                encoding="utf-8",
            )
            env["TRADER_MCP_TRADER_CONFIG_PATH"] = str(config_path)
            async with PersistentStdioMcpToolClient(
                command=sys.executable,
                args=["-m", "tests.support.mcp_sample_loading_server"],
                cwd=repo_root,
                env=env,
                read_timeout_seconds=10,
            ) as client:
                graph = build_data_agent_workflow_graph(client)
                output = await graph.ainvoke(_state(load_mode="sample", allow_data_loading=True))

        assert output["status"] == "completed"
        assert output["dataset_manifest"]["total_rows"] == 0
        assert output["initial_quality_report"]["complete"] is False
        assert output["load_result"]["mode"] == "sample"
        assert output["load_result"]["post_load_manifest"]["total_rows"] == 12
        assert output["final_quality_report"]["complete"] is True
        assert output["final_quality_report"]["total_bars"] == 12
        assert output["called_tools"] == [
            DATA_DISCOVER_SYMBOLS_TOOL,
            DATA_GET_INVENTORY_TOOL,
            DATA_SUMMARIZE_QUALITY_TOOL,
            DATA_ENSURE_LOADED_TOOL,
            DATA_SUMMARIZE_QUALITY_TOOL,
        ]

    anyio.run(_run)


def test_trader_agents_still_do_not_import_platform_or_mcp_server_boundaries() -> None:
    forbidden = (
        "trader.event_store",
        "trader.market_data.queries",
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
