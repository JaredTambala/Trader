"""Reusable interruption doubles for Agent runtime contract tests.

Subject: Deterministic MCP and model collaborators that expose interruption and cleanup behavior.
Level: Test support.
Collaborators: In-memory response queues and explicit process-fault exceptions; no external service.
Guarantees: Runtime tests can stop at precise transport or model boundaries and inspect terminal handling.
Non-goals: Modeling provider quality, MCP protocol fidelity, subprocess behavior, or production retries.
Cohesion rationale: These doubles share the single purpose of injecting bounded runtime interruptions."""

from __future__ import annotations
import asyncio
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any
from trader_agents import McpToolDescription


@dataclass
class _FakeMcpClient:
    """Small MCP transport fake with one Data inventory operation."""

    async def list_tools(self) -> Sequence[McpToolDescription]:
        """Return the exact test input schema."""
        return (
            McpToolDescription(
                name="data_get_inventory",
                description="Inspect data inventory.",
                input_schema={
                    "type": "object",
                    "required": [
                        "symbols",
                        "asset_class",
                        "timeframe",
                        "start",
                        "end",
                    ],
                    "properties": {
                        "symbols": {"type": "array"},
                        "asset_class": {"type": "string"},
                        "timeframe": {"type": "string"},
                        "start": {"type": "string"},
                        "end": {"type": "string"},
                    },
                    "additionalProperties": False,
                },
            ),
        )

    async def call_tool(
        self,
        tool_name: str,
        arguments: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        """Return a valid bounded MCP application envelope."""
        assert tool_name == "data_get_inventory"
        assert arguments["symbols"] == ["BTC/USD", "ETH/USD"]
        return {
            "structuredContent": {
                "ok": True,
                "command": tool_name,
                "agent_owner": "Data Agent",
                "side_effect": "read_only",
                "data": {"coverage": "complete"},
                "artifacts": {},
                "warnings": [],
                "errors": [],
            },
            "isError": False,
        }


class _TestProcessFault(BaseException):
    """Test-only process interruption outside agent exception handling."""


@dataclass
class _InterruptingMcpClient(_FakeMcpClient):
    """Expose a valid schema then interrupt instead of returning a response."""

    async def call_tool(
        self,
        tool_name: str,
        arguments: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        """Raise a process-level fault after runtime authorization."""
        del tool_name, arguments
        raise _TestProcessFault


@dataclass
class _InterruptingJsonLlmClient:
    """Return configured JSON, then simulate abrupt process cancellation."""

    responses: Sequence[Mapping[str, Any]]

    def __post_init__(self) -> None:
        """Copy responses so tests can safely reuse their input fixtures."""
        self._responses = [dict(response) for response in self.responses]

    async def complete_json(self, _: Any) -> Mapping[str, Any]:
        """Return one response or interrupt before another model result."""
        if not self._responses:
            raise asyncio.CancelledError
        return self._responses.pop(0)
