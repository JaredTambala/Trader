"""Contract tests for converting research results into MCP responses.

Subject: Protocol conversion from application or transport envelopes to MCP result mappings.
Level: Contract.
Collaborators: Real MCP protocol values and deterministic research result values.
Guarantees: Success, failure, metadata, and JSON-native values retain their public meaning.
Non-goals: Tool registration, stdio transport, capability execution, or agent interpretation.
"""

from __future__ import annotations

import json

from trader_mcp.protocol.adapters import result_to_mcp_result
from trader_mcp.protocol.contracts import SideEffect, error_envelope, success_envelope
from trader_research.foundation import success_result


def test_successful_envelope_converts_to_mcp_result() -> None:
    """Expose successful envelopes through matching text and structured MCP content."""
    envelope = success_envelope(
        command="data_get_inventory",
        side_effect=SideEffect.READ_ONLY,
        data={"dataset_id": "dataset_demo"},
    )

    result = result_to_mcp_result(envelope)

    assert result["isError"] is False
    assert result["structuredContent"]["agent_owner"] == "Data Agent"
    assert result["structuredContent"]["data"] == {"dataset_id": "dataset_demo"}
    assert result["content"][0]["type"] == "text"
    assert json.loads(result["content"][0]["text"]) == result["structuredContent"]


def test_failed_envelope_converts_to_error_mcp_result() -> None:
    """Expose failed envelopes as MCP errors with structured public details."""
    envelope = error_envelope(
        command="data_get_inventory",
        side_effect=SideEffect.READ_ONLY,
        code="missing_data",
        message="No bars found.",
    )

    result = result_to_mcp_result(envelope)

    assert result["isError"] is True
    assert result["structuredContent"]["ok"] is False
    assert result["structuredContent"]["errors"] == [
        {"code": "missing_data", "message": "No bars found."}
    ]


def test_mcp_result_contains_only_json_native_values() -> None:
    """Normalize tuple data so every returned MCP value serializes natively."""
    envelope = success_envelope(
        command="data_get_inventory",
        side_effect=SideEffect.READ_ONLY,
        data={"symbols": ("DEMO",)},
    )
    result = result_to_mcp_result(envelope)

    serialized = json.dumps(result, sort_keys=True)
    parsed = json.loads(serialized)

    assert parsed["structuredContent"]["data"] == {"symbols": ["DEMO"]}


def test_application_result_gains_transport_metadata_at_mcp_boundary() -> None:
    """Attach registered owner and side-effect metadata at protocol conversion time."""
    result = success_result(
        command="data_get_inventory",
        data={"dataset_id": "dataset_demo"},
    )

    mcp_result = result_to_mcp_result(result)

    assert mcp_result["structuredContent"]["agent_owner"] == "Data Agent"
    assert mcp_result["structuredContent"]["side_effect"] == "read_only"
