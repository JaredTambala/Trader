from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import anyio

from tests.support.duckdb_store import DuckDBEventStore
from trader.data import NoOpEventStore
from trader.sample_data import load_sample_market_data_csv
from trader_mcp.constants import (
    DATA_GET_INVENTORY_TOOL,
    MCP_CONFIG_TOOL,
    REGISTERED_TOOL_NAMES,
    UNREGISTERED_CAPABILITY_FLAGS,
)
from trader_mcp.environment import load_local_environment
from trader_mcp.server import create_server


SAMPLE_CSV = Path("examples/data/demo_stock_1min.csv")


def _inventory_args(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "symbols": ["DEMO"],
        "asset_class": "stocks",
        "timeframe": "1Min",
        "start": "2026-01-20T12:00:00Z",
        "end": "2026-01-20T12:11:00Z",
    }
    payload.update(overrides)
    return payload


def test_server_registers_inventory_tool_with_injected_event_store(tmp_path: Path) -> None:
    store = DuckDBEventStore(str(tmp_path / "events.duckdb"))
    server = create_server(load_local_environment(), event_store_provider=lambda: store)

    async def _run() -> None:
        tools = await server.list_tools()

        assert {tool.name for tool in tools} == set(REGISTERED_TOOL_NAMES)
        assert DATA_GET_INVENTORY_TOOL in {tool.name for tool in tools}

    anyio.run(_run)


def test_data_inventory_mcp_tool_returns_sample_manifest(tmp_path: Path) -> None:
    store = DuckDBEventStore(str(tmp_path / "events.duckdb"))
    load_sample_market_data_csv(store, SAMPLE_CSV)
    server = create_server(load_local_environment(), event_store_provider=lambda: store)

    async def _run() -> None:
        result = await server.call_tool(DATA_GET_INVENTORY_TOOL, _inventory_args())

        assert result.isError is False
        assert result.structuredContent is not None
        assert result.structuredContent["ok"] is True
        assert result.structuredContent["agent_owner"] == "Data Agent"
        assert result.structuredContent["side_effect"] == "read_only"
        manifest = result.structuredContent["data"]["dataset_manifest"]
        assert manifest["symbols"] == ["DEMO"]
        assert manifest["total_rows"] == 12
        assert manifest["complete"] is True
        assert manifest["symbols_detail"] == [
            {
                "symbol": "DEMO",
                "row_count": 12,
                "first_ts": "2026-01-20T12:00:00+00:00",
                "last_ts": "2026-01-20T12:11:00+00:00",
                "sources": {"sample": 12},
            }
        ]

    anyio.run(_run)


def test_data_inventory_mcp_tool_rejects_invalid_datetime(tmp_path: Path) -> None:
    store = DuckDBEventStore(str(tmp_path / "events.duckdb"))
    server = create_server(load_local_environment(), event_store_provider=lambda: store)

    async def _run() -> None:
        result = await server.call_tool(DATA_GET_INVENTORY_TOOL, _inventory_args(start="not-a-date"))

        assert result.isError is True
        assert result.structuredContent is not None
        assert result.structuredContent["ok"] is False
        assert result.structuredContent["errors"][0]["code"] == "validation_error"
        assert "start must be an ISO-8601 timestamp string" in result.structuredContent["errors"][0]["message"]

    anyio.run(_run)


def test_data_inventory_mcp_tool_rejects_invalid_timeframe(tmp_path: Path) -> None:
    store = DuckDBEventStore(str(tmp_path / "events.duckdb"))
    server = create_server(load_local_environment(), event_store_provider=lambda: store)

    async def _run() -> None:
        result = await server.call_tool(DATA_GET_INVENTORY_TOOL, _inventory_args(timeframe="bad"))

        assert result.isError is True
        assert result.structuredContent is not None
        assert result.structuredContent["ok"] is False
        assert result.structuredContent["errors"][0]["code"] == "validation_error"
        assert "Invalid timeframe" in result.structuredContent["errors"][0]["message"]

    anyio.run(_run)


def test_data_inventory_mcp_tool_reports_unavailable_connection() -> None:
    server = create_server(load_local_environment(), event_store_provider=NoOpEventStore)

    async def _run() -> None:
        result = await server.call_tool(DATA_GET_INVENTORY_TOOL, _inventory_args())

        assert result.isError is True
        assert result.structuredContent is not None
        assert result.structuredContent["ok"] is False
        assert result.structuredContent["errors"][0]["code"] == "event_store_connection_unavailable"

    anyio.run(_run)


def test_config_output_includes_inventory_and_excludes_mutating_tools() -> None:
    server = create_server(load_local_environment(), event_store_provider=NoOpEventStore)

    async def _run() -> None:
        result = await server.call_tool(MCP_CONFIG_TOOL, {})

        assert result.structuredContent is not None
        data = result.structuredContent["data"]
        tool_names = {tool["name"] for tool in data["tools"]}
        assert DATA_GET_INVENTORY_TOOL in tool_names
        assert "research_run_backtest" not in tool_names
        assert "data_ensure_loaded" not in tool_names
        assert data["safety"] == UNREGISTERED_CAPABILITY_FLAGS

    anyio.run(_run)


def test_data_inventory_mcp_tool_treats_naive_datetimes_as_utc(tmp_path: Path) -> None:
    store = DuckDBEventStore(str(tmp_path / "events.duckdb"))
    load_sample_market_data_csv(store, SAMPLE_CSV)
    server = create_server(load_local_environment(), event_store_provider=lambda: store)

    async def _run() -> None:
        result = await server.call_tool(
            DATA_GET_INVENTORY_TOOL,
            _inventory_args(
                start=datetime(2026, 1, 20, 12, 0).isoformat(),
                end=datetime(2026, 1, 20, 12, 11, tzinfo=timezone.utc).isoformat(),
            ),
        )

        assert result.isError is False
        assert result.structuredContent is not None
        manifest = result.structuredContent["data"]["dataset_manifest"]
        assert manifest["total_rows"] == 12

    anyio.run(_run)
