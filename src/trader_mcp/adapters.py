"""Adapters from research contracts to MCP-compatible result mappings."""

from __future__ import annotations

import json
from typing import Any

from trader_research.contracts import ToolEnvelope, envelope_json


def envelope_to_mcp_result(envelope: ToolEnvelope) -> dict[str, Any]:
    """Convert a research tool envelope to an MCP CallToolResult-style mapping.

    Args:
        envelope: Research tool envelope to expose through MCP.

    Returns:
        Dictionary with MCP-style `content`, `structuredContent`, and `isError`
        fields.
    """
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
