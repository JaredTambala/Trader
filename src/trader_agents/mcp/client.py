"""MCP transport clients used by the model-backed agent runtime."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from types import TracebackType
from typing import Any, Protocol

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


class McpToolClient(Protocol):
    """Minimal async MCP tool client protocol for agent graph nodes."""

    async def call_tool(
        self, tool_name: str, arguments: Mapping[str, Any]
    ) -> Mapping[str, Any]:
        """Call an MCP tool.

        Args:
            tool_name: MCP tool name to call.
            arguments: JSON-native tool arguments.

        Returns:
            MCP-style result mapping with `content`, `structuredContent`, and
            `isError` fields.
        """

    async def list_tools(self) -> Sequence["McpToolDescription"]:
        """Return the MCP server's current public tool schemas."""


@dataclass(frozen=True)
class McpToolDescription:
    """Bounded transport description for one registered MCP operation."""

    name: str
    description: str
    input_schema: Mapping[str, Any]
    output_schema: Mapping[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-native model-facing tool description."""
        payload = {
            "name": self.name,
            "description": self.description,
            "input_schema": dict(self.input_schema),
        }
        if self.output_schema is not None:
            payload["output_schema"] = dict(self.output_schema)
        return payload


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

    async def call_tool(
        self, tool_name: str, arguments: Mapping[str, Any]
    ) -> Mapping[str, Any]:
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

    async def list_tools(self) -> Sequence[McpToolDescription]:
        """List current MCP tool schemas through one isolated stdio session."""
        server_params = self._server_parameters()
        async with stdio_client(server_params) as (read_stream, write_stream):
            async with ClientSession(
                read_stream,
                write_stream,
                read_timeout_seconds=timedelta(seconds=self.read_timeout_seconds),
            ) as session:
                await session.initialize()
                result = await session.list_tools()
        return tuple(_tool_description(item) for item in result.tools)

    def _server_parameters(self) -> StdioServerParameters:
        """Build the exact stdio server process parameters."""
        return StdioServerParameters(
            command=self.command,
            args=list(self.args),
            cwd=self.cwd,
            env=dict(self.env) if self.env is not None else None,
        )


@dataclass
class PersistentStdioMcpToolClient:
    """MCP client that keeps one stdio server session open across calls.

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

    def __post_init__(self) -> None:
        """Initialize runtime context-manager handles."""
        self._stdio_context: Any | None = None
        self._session_context: Any | None = None
        self._session: ClientSession | None = None

    async def __aenter__(self) -> "PersistentStdioMcpToolClient":
        """Start the stdio server and initialize the MCP session.

        Returns:
            Initialized persistent MCP client.
        """
        server_params = StdioServerParameters(
            command=self.command,
            args=list(self.args),
            cwd=self.cwd,
            env=dict(self.env) if self.env is not None else None,
        )
        self._stdio_context = stdio_client(server_params)
        read_stream, write_stream = await self._stdio_context.__aenter__()
        self._session_context = ClientSession(
            read_stream,
            write_stream,
            read_timeout_seconds=timedelta(seconds=self.read_timeout_seconds),
        )
        try:
            self._session = await self._session_context.__aenter__()
            await self._session.initialize()
        except BaseException:
            await self.__aexit__(None, None, None)
            raise
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> bool:
        """Close the MCP session and stdio server.

        Args:
            exc_type: Exception type from the managed block.
            exc: Exception from the managed block.
            tb: Traceback from the managed block.

        Returns:
            False so exceptions propagate normally.
        """
        del exc_type, exc, tb
        try:
            if self._session_context is not None:
                # MCP and AnyIO own nested task-group cancel scopes. Close
                # those resources normally, then let this wrapper return false
                # so the caller's primary exception propagates unchanged.
                await self._session_context.__aexit__(None, None, None)
        finally:
            try:
                if self._stdio_context is not None:
                    await self._stdio_context.__aexit__(None, None, None)
            finally:
                self._session = None
                self._session_context = None
                self._stdio_context = None
        return False

    async def call_tool(
        self, tool_name: str, arguments: Mapping[str, Any]
    ) -> Mapping[str, Any]:
        """Call one MCP tool over the persistent session.

        Args:
            tool_name: MCP tool name to call.
            arguments: JSON-native tool arguments.

        Returns:
            MCP-style result mapping with JSON-safe content blocks and structured
            content.

        Raises:
            RuntimeError: If the client is used outside its async context.
        """
        if self._session is None:
            raise RuntimeError(
                "PersistentStdioMcpToolClient must be used as an async context manager"
            )
        result = await self._session.call_tool(tool_name, dict(arguments))
        return {
            "content": [_content_block_to_dict(block) for block in result.content],
            "structuredContent": dict(result.structuredContent or {}),
            "isError": bool(result.isError),
        }

    async def list_tools(self) -> Sequence[McpToolDescription]:
        """List current MCP tool schemas over the persistent session."""
        if self._session is None:
            raise RuntimeError(
                "PersistentStdioMcpToolClient must be used as an async context manager"
            )
        result = await self._session.list_tools()
        return tuple(_tool_description(item) for item in result.tools)


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


def _tool_description(tool: object) -> McpToolDescription:
    """Normalize one MCP SDK tool descriptor at the transport boundary."""
    name = str(getattr(tool, "name", "") or "").strip()
    if not name:
        raise ValueError("MCP tool descriptor is missing a name")
    description = str(getattr(tool, "description", "") or "").strip()
    input_schema = getattr(tool, "inputSchema", None)
    if not isinstance(input_schema, Mapping):
        raise ValueError(f"MCP tool {name} has no input schema")
    output_schema = getattr(tool, "outputSchema", None)
    return McpToolDescription(
        name=name,
        description=description,
        input_schema=dict(input_schema),
        output_schema=(
            dict(output_schema) if isinstance(output_schema, Mapping) else None
        ),
    )
