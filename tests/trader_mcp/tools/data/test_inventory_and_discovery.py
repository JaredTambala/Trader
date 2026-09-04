"""Adapter tests for MCP Data inventory and symbol discovery tools.

Subject: Data tool registration, inventory, discovery, validation, and provider policy.
Level: Adapter integration.
Collaborators: Real MCP adapters with DuckDB or unavailable event-store collaborators.
Guarantees: Public Data envelopes preserve scope, quality, validation, and safety evidence.
Non-goals: Data loading mutation, stdio transport, live providers, or agent reasoning.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import anyio

from tests.support.duckdb_store import DuckDBEventStore
from trader.event_store import NoOpEventStore
from trader.market_data.sample import load_sample_market_data_csv
from trader_mcp.catalogue.definitions import (
    CAPABILITY_REGISTRATION_FLAGS,
    DATA_CREATE_RESEARCH_SNAPSHOT_TOOL,
    DATA_DISCOVER_SYMBOLS_TOOL,
    DATA_ENSURE_LOADED_TOOL,
    DATA_GET_INVENTORY_TOOL,
    DATA_SUMMARIZE_QUALITY_TOOL,
    MCP_CONFIG_TOOL,
    REGISTERED_TOOL_NAMES,
)
from trader_mcp.catalogue.policy import load_local_environment
from trader_mcp.runtime.server import create_server


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


def test_server_registers_inventory_tool_with_injected_event_store(
    tmp_path: Path,
) -> None:
    """Register the inventory capability when an event-store provider is injected."""
    store = DuckDBEventStore(str(tmp_path / "events.duckdb"))
    server = create_server(
        load_local_environment("env.template"), event_store_provider=lambda: store
    )

    async def _run() -> None:
        tools = await server.list_tools()

        assert {tool.name for tool in tools} == set(REGISTERED_TOOL_NAMES)
        assert DATA_GET_INVENTORY_TOOL in {tool.name for tool in tools}

    anyio.run(_run)


def test_data_inventory_mcp_tool_returns_sample_manifest(tmp_path: Path) -> None:
    """Return complete per-symbol inventory evidence for deterministic sample bars."""
    store = DuckDBEventStore(str(tmp_path / "events.duckdb"))
    load_sample_market_data_csv(store, SAMPLE_CSV)
    server = create_server(
        load_local_environment("env.template"), event_store_provider=lambda: store
    )

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


def test_data_discover_symbols_mcp_tool_returns_local_report(tmp_path: Path) -> None:
    """Report local coverage and missing symbols through the discovery envelope."""
    store = DuckDBEventStore(str(tmp_path / "events.duckdb"))
    load_sample_market_data_csv(store, SAMPLE_CSV)
    server = create_server(
        load_local_environment("env.template"), event_store_provider=lambda: store
    )

    async def _run() -> None:
        result = await server.call_tool(
            DATA_DISCOVER_SYMBOLS_TOOL,
            {
                "symbols": ["DEMO", "MISSING"],
                "asset_class": "stocks",
                "source": "local",
                "include_local_coverage": True,
            },
        )

        assert result.isError is False
        assert result.structuredContent is not None
        report = result.structuredContent["data"]["symbol_discovery_report"]
        assert report["all_requested_symbols_exist"] is False
        assert report["missing_symbols"] == ["MISSING"]
        assert report["symbols"][0]["symbol"] == "DEMO"
        assert report["symbols"][0]["local_coverage"]["row_count"] == 12

    anyio.run(_run)


def test_data_discover_symbols_mcp_tool_rejects_provider_without_policy(
    tmp_path: Path,
) -> None:
    """Reject provider discovery before querying when policy forbids external access."""
    store = DuckDBEventStore(str(tmp_path / "events.duckdb"))
    server = create_server(
        load_local_environment("env.template"), event_store_provider=lambda: store
    )

    async def _run() -> None:
        result = await server.call_tool(
            DATA_DISCOVER_SYMBOLS_TOOL,
            {
                "symbols": ["DEMO"],
                "asset_class": "stocks",
                "source": "provider",
            },
        )

        assert result.isError is True
        assert result.structuredContent is not None
        assert (
            result.structuredContent["errors"][0]["code"]
            == "provider_discovery_not_allowed"
        )

    anyio.run(_run)


def test_data_inventory_mcp_tool_rejects_provider_mismatch_before_query(
    tmp_path: Path,
) -> None:
    """Reject a requested provider that differs from configured market data."""
    store = DuckDBEventStore(str(tmp_path / "events.duckdb"))
    server = create_server(
        load_local_environment("env.template"), event_store_provider=lambda: store
    )

    async def _run() -> None:
        result = await server.call_tool(
            DATA_GET_INVENTORY_TOOL,
            _inventory_args(provider="polygon"),
        )

        assert result.isError is True
        assert result.structuredContent is not None
        assert (
            result.structuredContent["errors"][0]["code"] == "provider_not_configured"
        )
        assert result.structuredContent["data"]["requested_provider"] == "polygon"
        assert result.structuredContent["data"]["configured_provider"] == "alpaca"

    anyio.run(_run)


def test_data_inventory_mcp_tool_rejects_invalid_datetime(tmp_path: Path) -> None:
    """Return a structured validation error for malformed inventory timestamps."""
    store = DuckDBEventStore(str(tmp_path / "events.duckdb"))
    server = create_server(
        load_local_environment("env.template"), event_store_provider=lambda: store
    )

    async def _run() -> None:
        result = await server.call_tool(
            DATA_GET_INVENTORY_TOOL, _inventory_args(start="not-a-date")
        )

        assert result.isError is True
        assert result.structuredContent is not None
        assert result.structuredContent["ok"] is False
        assert result.structuredContent["errors"][0]["code"] == "validation_error"
        assert (
            "start must be an ISO-8601 timestamp string"
            in result.structuredContent["errors"][0]["message"]
        )

    anyio.run(_run)


def test_data_inventory_mcp_tool_rejects_invalid_timeframe(tmp_path: Path) -> None:
    """Return a structured validation error for unsupported inventory timeframes."""
    store = DuckDBEventStore(str(tmp_path / "events.duckdb"))
    server = create_server(
        load_local_environment("env.template"), event_store_provider=lambda: store
    )

    async def _run() -> None:
        result = await server.call_tool(
            DATA_GET_INVENTORY_TOOL, _inventory_args(timeframe="bad")
        )

        assert result.isError is True
        assert result.structuredContent is not None
        assert result.structuredContent["ok"] is False
        assert result.structuredContent["errors"][0]["code"] == "validation_error"
        assert "Invalid timeframe" in result.structuredContent["errors"][0]["message"]

    anyio.run(_run)


def test_data_inventory_mcp_tool_reports_unavailable_connection() -> None:
    """Report event-store unavailability without inventing an empty successful manifest."""
    server = create_server(
        load_local_environment("env.template"), event_store_provider=NoOpEventStore
    )

    async def _run() -> None:
        result = await server.call_tool(DATA_GET_INVENTORY_TOOL, _inventory_args())

        assert result.isError is True
        assert result.structuredContent is not None
        assert result.structuredContent["ok"] is False
        assert (
            result.structuredContent["errors"][0]["code"]
            == "event_store_connection_unavailable"
        )

    anyio.run(_run)


def test_config_output_includes_data_tools_and_excludes_unsafe_tools() -> None:
    """Publish registered Data capabilities while excluding unsafe legacy operations."""
    server = create_server(
        load_local_environment("env.template"), event_store_provider=NoOpEventStore
    )

    async def _run() -> None:
        result = await server.call_tool(MCP_CONFIG_TOOL, {})

        assert result.structuredContent is not None
        data = result.structuredContent["data"]
        tool_names = {tool["name"] for tool in data["tools"]}
        assert DATA_DISCOVER_SYMBOLS_TOOL in tool_names
        assert DATA_GET_INVENTORY_TOOL in tool_names
        assert DATA_SUMMARIZE_QUALITY_TOOL in tool_names
        assert DATA_ENSURE_LOADED_TOOL in tool_names
        assert DATA_CREATE_RESEARCH_SNAPSHOT_TOOL in tool_names
        assert "research_run_backtest_specification" in tool_names
        assert "research_run_backtest" not in tool_names
        assert data["safety"] == {
            **CAPABILITY_REGISTRATION_FLAGS,
            "symbol_provider_discovery_allowed": False,
            "data_loading_mutation_allowed": False,
            "backtest_execution_allowed": False,
            "optimization_execution_allowed": False,
            "external_research_writes_allowed": False,
            "optuna_writes_allowed": False,
            "experiment_tracking_writes_allowed": False,
            "ml_runtime_allowed": False,
            "coding_workspace_allowed": False,
        }

    anyio.run(_run)


def test_data_inventory_mcp_tool_treats_naive_datetimes_as_utc(tmp_path: Path) -> None:
    """Normalize naive inventory timestamps to UTC before querying stored bars."""
    store = DuckDBEventStore(str(tmp_path / "events.duckdb"))
    load_sample_market_data_csv(store, SAMPLE_CSV)
    server = create_server(
        load_local_environment("env.template"), event_store_provider=lambda: store
    )

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
