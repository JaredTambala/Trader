"""Tests for protocol-safe MCP subprocess console logging."""

from __future__ import annotations

from io import StringIO
import json

import pytest

from trader_mcp.console_logging import (
    McpConsoleConfig,
    McpConsoleLogger,
    McpLogFormat,
    McpLogLevel,
    mcp_console_config,
)


def test_mcp_console_config_defaults_and_normalizes_environment() -> None:
    """MCP logging defaults to INFO human and accepts DEBUG JSON."""
    assert mcp_console_config({}).level is McpLogLevel.INFO
    assert mcp_console_config({}).format is McpLogFormat.HUMAN

    config = mcp_console_config(
        {
            "TRADER_MCP_LOG_LEVEL": "DEBUG",
            "TRADER_MCP_LOG_FORMAT": "JSON",
            "TRADER_MCP_SERVER_ROLE": "data_research",
        }
    )

    assert config.level is McpLogLevel.DEBUG
    assert config.format is McpLogFormat.JSON
    assert config.role == "data_research"


@pytest.mark.parametrize(
    ("environment", "message"),
    [
        ({"TRADER_MCP_LOG_LEVEL": "WARNING"}, "DEBUG or INFO"),
        ({"TRADER_MCP_LOG_FORMAT": "yaml"}, "human or json"),
        ({"TRADER_MCP_SERVER_ROLE": ""}, "role is required"),
    ],
)
def test_mcp_console_config_rejects_invalid_values(
    environment: dict[str, str],
    message: str,
) -> None:
    """Invalid subprocess logging configuration fails before server startup."""
    with pytest.raises(ValueError, match=message):
        mcp_console_config(environment)


def test_info_human_output_is_role_and_process_labelled() -> None:
    """The default MCP line is readable and contains concurrency identities."""
    stream = StringIO()
    logger = McpConsoleLogger(
        config=McpConsoleConfig(
            role="strategy_engineering",
            process_instance_id="mcp-process-1",
        ),
        stream=stream,
    )

    logger.debug("trader.mcp.server.configured", tool_count=90)
    logger.info("trader.mcp.server.started", transport="stdio", tool_count=90)

    output = stream.getvalue()
    assert output.count("\n") == 1
    assert "INFO trader.mcp.server.started" in output
    assert "role=strategy_engineering" in output
    assert "process=mcp-process-1" in output
    assert 'transport="stdio"' in output


def test_debug_json_output_is_one_parseable_event_per_line() -> None:
    """DEBUG mode exposes bounded process detail as JSON on its assigned stream."""
    stream = StringIO()
    logger = McpConsoleLogger(
        config=McpConsoleConfig(
            level=McpLogLevel.DEBUG,
            format=McpLogFormat.JSON,
            role="data_research",
            process_instance_id="mcp-process-2",
        ),
        stream=stream,
    )

    logger.debug("trader.mcp.server.configured", tool_count=90)

    payload = json.loads(stream.getvalue())
    assert payload == {
        "event": "trader.mcp.server.configured",
        "level": "debug",
        "process_instance_id": "mcp-process-2",
        "role": "data_research",
        "tool_count": 90,
    }


def test_mcp_console_rejects_secret_bearing_fields() -> None:
    """A subprocess log cannot accidentally admit credential-shaped fields."""
    logger = McpConsoleLogger(stream=StringIO())

    with pytest.raises(ValueError, match="not allowed"):
        logger.info("trader.mcp.server.started", api_key="do-not-log")
