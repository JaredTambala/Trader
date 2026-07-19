from __future__ import annotations

import json

from trader_mcp.adapters import result_to_mcp_result
from trader_mcp.contracts import SideEffect, error_envelope, success_envelope
from trader_research.foundation import success_result


def test_successful_envelope_converts_to_mcp_result() -> None:
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
    envelope = error_envelope(
        command="data_get_inventory",
        side_effect=SideEffect.READ_ONLY,
        code="missing_data",
        message="No bars found.",
    )

    result = result_to_mcp_result(envelope)

    assert result["isError"] is True
    assert result["structuredContent"]["ok"] is False
    assert result["structuredContent"]["errors"] == [{"code": "missing_data", "message": "No bars found."}]


def test_mcp_result_contains_only_json_native_values() -> None:
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
    result = success_result(
        command="data_get_inventory",
        data={"dataset_id": "dataset_demo"},
    )

    mcp_result = result_to_mcp_result(result)

    assert mcp_result["structuredContent"]["agent_owner"] == "Data Agent"
    assert mcp_result["structuredContent"]["side_effect"] == "read_only"
