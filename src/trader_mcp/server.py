"""Stdio MCP server skeleton for research tools."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import datetime, timezone

from mcp.server.fastmcp import FastMCP
from mcp.types import CallToolResult

from trader.config import build_config, load_yaml_config
from trader.data import EventStore, NoOpEventStore, build_event_store
from trader_mcp.adapters import envelope_to_mcp_result
from trader_mcp.constants import (
    DATA_GET_INVENTORY_TOOL,
    DATA_TOOL_DESCRIPTIONS,
    MCP_CONFIG_TOOL,
    MCP_HEALTH_TOOL,
    MCP_SERVER_OWNER,
    REGISTERED_TOOL_NAMES,
    SERVER_NAME,
    SUPPORT_TOOL_DESCRIPTIONS,
    UNREGISTERED_CAPABILITY_FLAGS,
)
from trader_mcp.environment import McpEnvironment, load_local_environment
from trader_research.agents import agent_owner_for_tool
from trader_research.contracts import SCHEMA_VERSION, SideEffect, ToolEnvelope, error_envelope, success_envelope
from trader_research.data import DataInventoryRequest, get_data_inventory


EventStoreProvider = Callable[[], EventStore]
"""Callable that returns the event store used by read-only MCP tools."""


def create_server(
    environment: McpEnvironment | None = None,
    event_store_provider: EventStoreProvider | None = None,
) -> FastMCP:
    """Create the MCP server and register read-only tools.

    Args:
        environment: Optional resolved local MCP environment.
        event_store_provider: Optional provider for read-only event-store queries.

    Returns:
        Configured FastMCP server instance.
    """
    local_env = environment or load_local_environment()
    data_event_store_provider = event_store_provider or build_event_store_provider(local_env)
    server = FastMCP(SERVER_NAME)

    @server.tool(name=MCP_HEALTH_TOOL, description=SUPPORT_TOOL_DESCRIPTIONS[MCP_HEALTH_TOOL])
    def mcp_health() -> CallToolResult:
        """Return read-only MCP server health.

        Returns:
            MCP call result containing a read-only health envelope.
        """
        return CallToolResult(**envelope_to_mcp_result(build_health_envelope(local_env)))

    @server.tool(name=MCP_CONFIG_TOOL, description=SUPPORT_TOOL_DESCRIPTIONS[MCP_CONFIG_TOOL])
    def mcp_get_config() -> CallToolResult:
        """Return read-only MCP server configuration.

        Returns:
            MCP call result containing a read-only configuration envelope.
        """
        return CallToolResult(**envelope_to_mcp_result(build_config_envelope(local_env)))

    @server.tool(
        name=DATA_GET_INVENTORY_TOOL,
        description=DATA_TOOL_DESCRIPTIONS[DATA_GET_INVENTORY_TOOL],
    )
    def data_get_inventory(
        symbols: list[str],
        asset_class: str,
        timeframe: str,
        start: str,
        end: str,
        source: str | None = None,
    ) -> CallToolResult:
        """Return a read-only Data Agent inventory envelope.

        Args:
            symbols: JSON array of requested symbols.
            asset_class: Requested asset class.
            timeframe: Requested bar timeframe.
            start: Inclusive requested start timestamp as ISO-8601 text.
            end: Inclusive requested end timestamp as ISO-8601 text.
            source: Optional source filter.

        Returns:
            MCP call result containing a Data Agent inventory envelope.
        """
        envelope = build_data_inventory_envelope(
            event_store_provider=data_event_store_provider,
            symbols=symbols,
            asset_class=asset_class,
            timeframe=timeframe,
            start=start,
            end=end,
            source=source,
        )
        return CallToolResult(**envelope_to_mcp_result(envelope))

    return server


def build_event_store_provider(environment: McpEnvironment | None = None) -> EventStoreProvider:
    """Build the event-store provider used by read-only MCP tools.

    Args:
        environment: Optional resolved local MCP environment.

    Returns:
        Provider that returns a configured event store, or a no-op store when no
        trader config path is configured.
    """
    local_env = environment or load_local_environment()
    if local_env.trader_config_path is None:
        return NoOpEventStore
    config = build_config(load_yaml_config(local_env.trader_config_path))
    event_store = build_event_store(config)
    return lambda: event_store


def build_health_envelope(environment: McpEnvironment | None = None) -> ToolEnvelope:
    """Build the read-only MCP server health envelope.

    Args:
        environment: Optional resolved local MCP environment.

    Returns:
        Successful health envelope owned by the MCP server support boundary.
    """
    local_env = environment or load_local_environment()
    return success_envelope(
        command=MCP_HEALTH_TOOL,
        agent_owner=MCP_SERVER_OWNER,
        side_effect=SideEffect.READ_ONLY,
        data={
            "status": "ok",
            "environment": local_env.environment,
            "server_name": SERVER_NAME,
            "transport": local_env.transport,
            "schema_version": SCHEMA_VERSION,
            "tools": list(REGISTERED_TOOL_NAMES),
        },
    )


def build_config_envelope(environment: McpEnvironment | None = None) -> ToolEnvelope:
    """Build the read-only MCP server configuration envelope.

    Args:
        environment: Optional resolved local MCP environment.

    Returns:
        Successful configuration envelope owned by the MCP server support boundary.
    """
    local_env = environment or load_local_environment()
    tool_metadata = [
        {
            "name": MCP_HEALTH_TOOL,
            "agent_owner": MCP_SERVER_OWNER,
            "side_effect": SideEffect.READ_ONLY.value,
            "description": SUPPORT_TOOL_DESCRIPTIONS[MCP_HEALTH_TOOL],
        },
        {
            "name": MCP_CONFIG_TOOL,
            "agent_owner": MCP_SERVER_OWNER,
            "side_effect": SideEffect.READ_ONLY.value,
            "description": SUPPORT_TOOL_DESCRIPTIONS[MCP_CONFIG_TOOL],
        },
        {
            "name": DATA_GET_INVENTORY_TOOL,
            "agent_owner": agent_owner_for_tool(DATA_GET_INVENTORY_TOOL),
            "side_effect": SideEffect.READ_ONLY.value,
            "description": DATA_TOOL_DESCRIPTIONS[DATA_GET_INVENTORY_TOOL],
        },
    ]
    return success_envelope(
        command=MCP_CONFIG_TOOL,
        agent_owner=MCP_SERVER_OWNER,
        side_effect=SideEffect.READ_ONLY,
        data={
            "environment": local_env.environment,
            "server_name": SERVER_NAME,
            "transport": local_env.transport,
            "artifact_root": str(local_env.artifact_root),
            "trader_config_path": str(local_env.trader_config_path) if local_env.trader_config_path else None,
            "tool_count": len(tool_metadata),
            "tools": tool_metadata,
            "policy": local_env.policy_flags(),
            "safety": dict(UNREGISTERED_CAPABILITY_FLAGS),
        },
    )


def build_data_inventory_envelope(
    *,
    event_store_provider: EventStoreProvider,
    symbols: Sequence[str],
    asset_class: str,
    timeframe: str,
    start: str,
    end: str,
    source: str | None = None,
) -> ToolEnvelope:
    """Build a Data Agent inventory envelope from MCP-native inputs.

    Args:
        event_store_provider: Provider for read-only event-store queries.
        symbols: Requested symbol universe.
        asset_class: Requested asset class.
        timeframe: Requested bar timeframe.
        start: Inclusive requested start timestamp as ISO-8601 text.
        end: Inclusive requested end timestamp as ISO-8601 text.
        source: Optional source filter.

    Returns:
        Data Agent tool envelope for the requested inventory.
    """
    try:
        request = _data_inventory_request_from_inputs(
            symbols=symbols,
            asset_class=asset_class,
            timeframe=timeframe,
            start=start,
            end=end,
            source=source,
        )
    except ValueError as exc:
        return error_envelope(
            command=DATA_GET_INVENTORY_TOOL,
            side_effect=SideEffect.READ_ONLY,
            code="validation_error",
            message=str(exc),
        )
    return get_data_inventory(event_store_provider(), request)


def _data_inventory_request_from_inputs(
    *,
    symbols: Sequence[str],
    asset_class: str,
    timeframe: str,
    start: str,
    end: str,
    source: str | None,
) -> DataInventoryRequest:
    """Build a Data Agent inventory request from MCP tool inputs.

    Args:
        symbols: Requested symbol universe.
        asset_class: Requested asset class.
        timeframe: Requested bar timeframe.
        start: Inclusive requested start timestamp as ISO-8601 text.
        end: Inclusive requested end timestamp as ISO-8601 text.
        source: Optional source filter.

    Returns:
        Data inventory request with parsed datetimes.

    Raises:
        ValueError: If MCP inputs are not JSON-native values expected by the tool.
    """
    return DataInventoryRequest(
        symbols=_parse_symbols(symbols),
        asset_class=str(asset_class),
        timeframe=str(timeframe),
        start=_parse_iso_datetime(start, field_name="start"),
        end=_parse_iso_datetime(end, field_name="end"),
        source=str(source) if source is not None else None,
    )


def _parse_symbols(symbols: Sequence[str]) -> tuple[str, ...]:
    """Parse MCP symbol input into a tuple.

    Args:
        symbols: JSON array of requested symbols.

    Returns:
        Tuple of symbol strings.

    Raises:
        ValueError: If symbols are not supplied as a JSON array.
    """
    if isinstance(symbols, str) or not isinstance(symbols, Sequence):
        raise ValueError("symbols must be a JSON array of strings")
    return tuple(str(symbol) for symbol in symbols)


def _parse_iso_datetime(value: str, *, field_name: str) -> datetime:
    """Parse an ISO-8601 timestamp from MCP input.

    Args:
        value: Timestamp text.
        field_name: Input field name used in validation errors.

    Returns:
        Timezone-aware UTC datetime. Naive datetimes are treated as UTC.

    Raises:
        ValueError: If the value is not an ISO-8601 timestamp string.
    """
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be an ISO-8601 timestamp string")
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{field_name} must be an ISO-8601 timestamp string") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def main() -> None:
    """Run the MCP server over stdio transport."""
    local_env = load_local_environment()
    create_server(local_env).run(transport=local_env.transport)


if __name__ == "__main__":
    main()
