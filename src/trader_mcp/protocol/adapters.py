"""Adapters from research contracts to MCP-compatible result mappings."""

from __future__ import annotations

import json
from typing import Any

from trader_research.foundation import ApplicationResult

from .contracts import ToolEnvelope, envelope_json, result_to_envelope


def result_to_mcp_result(
    result: ApplicationResult | ToolEnvelope,
) -> dict[str, Any]:
    """Convert an application result to an MCP CallToolResult-style mapping.

    Args:
        result: Research result or MCP-owned envelope to expose through MCP.

    Returns:
        Dictionary with MCP-style `content`, `structuredContent`, and `isError`
        fields.
    """
    envelope = (
        result_to_envelope(result) if isinstance(result, ApplicationResult) else result
    )
    structured_content = envelope.to_dict()
    return {
        "content": [{"type": "text", "text": envelope_json(envelope)}],
        "structuredContent": structured_content,
        "isError": not envelope.ok,
    }


def mcp_result_json(result: dict[str, Any]) -> str:
    """Serialize an MCP result mapping as stable JSON.

    Args:
        result: MCP result mapping to serialize.

    Returns:
        Pretty JSON string with sorted keys.
    """
    return json.dumps(result, indent=2, sort_keys=True)
