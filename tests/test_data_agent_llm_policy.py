from __future__ import annotations

from typing import Any, Mapping

import anyio

from trader_mcp.constants import (
    DATA_DISCOVER_SYMBOLS_TOOL,
    DATA_ENSURE_LOADED_TOOL,
    DATA_GET_INVENTORY_TOOL,
    DATA_SUMMARIZE_QUALITY_TOOL,
)
from trader_agents.data_agent import build_data_agent_llm_policy_graph
from trader_agents.llm_client import StaticJsonLlmClient
from trader_agents.state import build_data_agent_initial_state


def _state(**overrides: object) -> dict[str, Any]:
    payload = {
        "symbols": ("DEMO",),
        "asset_class": "stocks",
        "timeframe": "1Min",
        "start": "2026-01-20T12:00:00Z",
        "end": "2026-01-20T12:11:00Z",
        "user_request": "Check whether DEMO stock data is available and clean.",
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


def _data_arguments(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "symbols": ["DEMO"],
        "asset_class": "stocks",
        "timeframe": "1Min",
        "start": "2026-01-20T12:00:00Z",
        "end": "2026-01-20T12:11:00Z",
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
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def call_tool(self, tool_name: str, arguments: Mapping[str, Any]) -> Mapping[str, Any]:
        self.calls.append((tool_name, dict(arguments)))
        raise AssertionError(f"unexpected tool call: {tool_name}")


def test_data_agent_llm_policy_graph_discovers_inventories_qualities_and_finishes() -> None:
    llm = StaticJsonLlmClient(
        [
            {
                "action": "discover_symbols",
                "tool_name": DATA_DISCOVER_SYMBOLS_TOOL,
                "arguments": {"symbols": ["DEMO"], "asset_class": "stocks", "timeframe": "1Min"},
                "reason": "Validate symbol availability before any data query.",
            },
            {
                "action": "inspect_inventory",
                "tool_name": DATA_GET_INVENTORY_TOOL,
                "arguments": _data_arguments(),
                "reason": "Inspect available local data.",
            },
            {
                "action": "summarize_quality",
                "tool_name": DATA_SUMMARIZE_QUALITY_TOOL,
                "arguments": _data_arguments(),
                "reason": "Summarize quality after inventory.",
            },
            {"action": "finish", "reason": "Inventory and quality evidence are complete."},
        ]
    )
    mcp = SequenceMcpToolClient(
        [
            _discovery_result(),
            _success_result(DATA_GET_INVENTORY_TOOL, "dataset_manifest", {"symbols": ["DEMO"], "total_rows": 12}),
            _success_result(DATA_SUMMARIZE_QUALITY_TOOL, "data_quality_report", {"complete": True, "total_bars": 12}),
        ]
    )
    graph = build_data_agent_llm_policy_graph(mcp, llm)

    async def _run() -> None:
        output = await graph.ainvoke(_state())

        assert output["status"] == "completed"
        assert output["dataset_manifest"]["total_rows"] == 12
        assert output["quality_report"]["complete"] is True
        assert output["called_tools"] == [
            DATA_DISCOVER_SYMBOLS_TOOL,
            DATA_GET_INVENTORY_TOOL,
            DATA_SUMMARIZE_QUALITY_TOOL,
        ]
        assert [call[0] for call in mcp.calls] == output["called_tools"]
        assert [decision["action"] for decision in output["llm_decisions"]] == [
            "discover_symbols",
            "inspect_inventory",
            "summarize_quality",
            "finish",
        ]
        assert "messages" not in output
        assert "prompt" not in output
        assert "scratchpad" not in output

    anyio.run(_run)


def test_data_agent_llm_policy_graph_fails_fast_when_llm_is_not_configured(monkeypatch: Any) -> None:
    for key in (
        "TRADER_AGENTS_LLM_PROVIDER",
        "TRADER_AGENTS_LLM_MODEL",
        "TRADER_AGENTS_LLM_BASE_URL",
        "TRADER_AGENTS_LLM_API_KEY",
    ):
        monkeypatch.delenv(key, raising=False)
    mcp = FailingIfCalledClient()
    graph = build_data_agent_llm_policy_graph(mcp)

    async def _run() -> None:
        output = await graph.ainvoke(_state())

        assert output["status"] == "blocked"
        assert output["blockers"][0]["code"] == "llm_not_configured"
        assert output["called_tools"] == []
        assert mcp.calls == []

    anyio.run(_run)


def test_data_agent_llm_policy_graph_rejects_invalid_tool_before_mcp_call() -> None:
    llm = StaticJsonLlmClient(
        [
            {
                "action": "inspect_inventory",
                "tool_name": "research_run_backtest",
                "arguments": _data_arguments(),
                "reason": "Try an invalid tool.",
            }
        ]
    )
    mcp = FailingIfCalledClient()
    graph = build_data_agent_llm_policy_graph(mcp, llm)

    async def _run() -> None:
        output = await graph.ainvoke(_state())

        assert output["status"] == "failed"
        assert output["errors"][0]["code"] == "invalid_llm_tool"
        assert output["called_tools"] == []
        assert mcp.calls == []

    anyio.run(_run)


def test_data_agent_llm_policy_graph_fails_closed_on_invalid_llm_output() -> None:
    llm = StaticJsonLlmClient([{"action": "finish"}])
    mcp = FailingIfCalledClient()
    graph = build_data_agent_llm_policy_graph(mcp, llm)

    async def _run() -> None:
        output = await graph.ainvoke(_state())

        assert output["status"] == "failed"
        assert output["errors"][0]["code"] == "invalid_llm_decision"
        assert output["called_tools"] == []
        assert mcp.calls == []

    anyio.run(_run)


def test_data_agent_llm_policy_graph_blocks_missing_symbols_before_downstream_tools() -> None:
    llm = StaticJsonLlmClient(
        [
            {
                "action": "discover_symbols",
                "tool_name": DATA_DISCOVER_SYMBOLS_TOOL,
                "arguments": {"symbols": ["MISSING"], "asset_class": "stocks", "timeframe": "1Min"},
                "reason": "Validate symbols.",
            },
            {
                "action": "inspect_inventory",
                "tool_name": DATA_GET_INVENTORY_TOOL,
                "arguments": _data_arguments(symbols=["MISSING"]),
                "reason": "This should not run.",
            },
        ]
    )
    mcp = SequenceMcpToolClient(
        [
            _discovery_result(
                all_requested_symbols_exist=False,
                missing_symbols=["MISSING"],
            )
        ]
    )
    graph = build_data_agent_llm_policy_graph(mcp, llm)

    async def _run() -> None:
        output = await graph.ainvoke(_state(symbols=("MISSING",)))

        assert output["status"] == "blocked"
        assert output["blockers"][0]["code"] == "symbols_not_available"
        assert output["called_tools"] == [DATA_DISCOVER_SYMBOLS_TOOL]
        assert [call[0] for call in mcp.calls] == [DATA_DISCOVER_SYMBOLS_TOOL]

    anyio.run(_run)


def test_data_agent_llm_policy_graph_rejects_unbounded_downstream_request_before_mcp_call() -> None:
    unbounded_arguments = _data_arguments()
    unbounded_arguments.pop("end")
    llm = StaticJsonLlmClient(
        [
            {
                "action": "discover_symbols",
                "tool_name": DATA_DISCOVER_SYMBOLS_TOOL,
                "arguments": {"symbols": ["DEMO"], "asset_class": "stocks", "timeframe": "1Min"},
                "reason": "Validate symbols.",
            },
            {
                "action": "inspect_inventory",
                "tool_name": DATA_GET_INVENTORY_TOOL,
                "arguments": unbounded_arguments,
                "reason": "Try an unbounded request.",
            },
        ]
    )
    mcp = SequenceMcpToolClient([_discovery_result()])
    graph = build_data_agent_llm_policy_graph(mcp, llm)

    async def _run() -> None:
        output = await graph.ainvoke(_state())

        assert output["status"] == "failed"
        assert output["errors"][0]["code"] == "unbounded_data_request"
        assert output["called_tools"] == [DATA_DISCOVER_SYMBOLS_TOOL]
        assert [call[0] for call in mcp.calls] == [DATA_DISCOVER_SYMBOLS_TOOL]

    anyio.run(_run)


def test_data_agent_llm_policy_graph_rejects_provider_context_mismatch_before_downstream_tool() -> None:
    llm = StaticJsonLlmClient(
        [
            {
                "action": "discover_symbols",
                "tool_name": DATA_DISCOVER_SYMBOLS_TOOL,
                "arguments": {"symbols": ["DEMO"], "asset_class": "stocks", "timeframe": "1Min"},
                "reason": "Validate symbols.",
            },
            {
                "action": "inspect_inventory",
                "tool_name": DATA_GET_INVENTORY_TOOL,
                "arguments": _data_arguments(provider="polygon"),
                "reason": "Try the wrong provider.",
            },
        ]
    )
    mcp = SequenceMcpToolClient([_discovery_result()])
    graph = build_data_agent_llm_policy_graph(mcp, llm)

    async def _run() -> None:
        output = await graph.ainvoke(_state())

        assert output["status"] == "failed"
        assert output["errors"][0]["code"] == "provider_context_mismatch"
        assert output["called_tools"] == [DATA_DISCOVER_SYMBOLS_TOOL]
        assert [call[0] for call in mcp.calls] == [DATA_DISCOVER_SYMBOLS_TOOL]

    anyio.run(_run)


def test_data_agent_llm_policy_graph_refuses_loading_when_policy_disallows_mutation() -> None:
    llm = StaticJsonLlmClient(
        [
            {
                "action": "discover_symbols",
                "tool_name": DATA_DISCOVER_SYMBOLS_TOOL,
                "arguments": {"symbols": ["DEMO"], "asset_class": "stocks", "timeframe": "1Min"},
                "reason": "Validate symbols.",
            },
            {
                "action": "ensure_loaded",
                "tool_name": DATA_ENSURE_LOADED_TOOL,
                "arguments": _data_arguments(mode="sample"),
                "reason": "Try loading without policy.",
            },
        ]
    )
    mcp = SequenceMcpToolClient([_discovery_result()])
    graph = build_data_agent_llm_policy_graph(mcp, llm)

    async def _run() -> None:
        output = await graph.ainvoke(_state(load_mode="sample", allow_data_loading=False))

        assert output["status"] == "failed"
        assert output["errors"][0]["code"] == "data_loading_not_allowed"
        assert output["called_tools"] == [DATA_DISCOVER_SYMBOLS_TOOL]
        assert [call[0] for call in mcp.calls] == [DATA_DISCOVER_SYMBOLS_TOOL]

    anyio.run(_run)


def test_data_agent_llm_policy_graph_enforces_loop_limit() -> None:
    llm = StaticJsonLlmClient(
        [
            {
                "action": "discover_symbols",
                "tool_name": DATA_DISCOVER_SYMBOLS_TOOL,
                "arguments": {"symbols": ["DEMO"], "asset_class": "stocks", "timeframe": "1Min"},
                "reason": "Validate symbols.",
            },
            {"action": "finish", "reason": "This should not be requested."},
        ]
    )
    mcp = SequenceMcpToolClient([_discovery_result()])
    graph = build_data_agent_llm_policy_graph(mcp, llm, max_policy_decisions=1)

    async def _run() -> None:
        output = await graph.ainvoke(_state())

        assert output["status"] == "blocked"
        assert output["blockers"][0]["code"] == "llm_loop_limit_exceeded"
        assert output["called_tools"] == [DATA_DISCOVER_SYMBOLS_TOOL]
        assert len(llm.requests) == 1

    anyio.run(_run)
