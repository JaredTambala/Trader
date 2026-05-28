"""MCP client wrappers used by deterministic agent graphs."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from typing import Any, Protocol

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


class McpToolClient(Protocol):
    """Minimal async MCP tool client protocol for agent graph nodes."""

    async def call_tool(self, tool_name: str, arguments: Mapping[str, Any]) -> Mapping[str, Any]:
        """Call an MCP tool.

        Args:
            tool_name: MCP tool name to call.
            arguments: JSON-native tool arguments.

        Returns:
            MCP-style result mapping with `content`, `structuredContent`, and
            `isError` fields.
        """


@dataclass(frozen=True)
class StdioMcpToolClient:
    """MCP client that starts a stdio server process for each tool call.

    Attributes:
        command: Executable used to start the MCP server.
        args: Command arguments.
        cwd: Optional working directory for the server process.
        env: Optional environment for the server process.
        read_timeout_seconds: Timeout applied to MCP reads.
    """

    command: str
    args: Sequence[str]
    cwd: str | Path | None = None
    env: Mapping[str, str] | None = None
    read_timeout_seconds: int = 10

    async def call_tool(self, tool_name: str, arguments: Mapping[str, Any]) -> Mapping[str, Any]:
        """Call one MCP tool over a stdio server process.

        Args:
            tool_name: MCP tool name to call.
            arguments: JSON-native tool arguments.

        Returns:
            MCP-style result mapping with JSON-safe content blocks and structured
            content.
        """
        server_params = StdioServerParameters(
            command=self.command,
            args=list(self.args),
            cwd=self.cwd,
            env=dict(self.env) if self.env is not None else None,
        )
        async with stdio_client(server_params) as (read_stream, write_stream):
            async with ClientSession(
                read_stream,
                write_stream,
                read_timeout_seconds=timedelta(seconds=self.read_timeout_seconds),
            ) as session:
                await session.initialize()
                result = await session.call_tool(tool_name, dict(arguments))
        return {
            "content": [_content_block_to_dict(block) for block in result.content],
            "structuredContent": dict(result.structuredContent or {}),
            "isError": bool(result.isError),
        }


def _content_block_to_dict(block: object) -> dict[str, Any]:
    """Convert an MCP content block to a JSON-safe mapping.

    Args:
        block: MCP content block object.

    Returns:
        JSON-safe content block mapping.
    """
    model_dump = getattr(block, "model_dump", None)
    if callable(model_dump):
        return dict(model_dump(mode="json"))
    if isinstance(block, Mapping):
        return dict(block)
    return {"type": "unknown", "text": str(block)}
