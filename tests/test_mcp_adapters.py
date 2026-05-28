from __future__ import annotations

import json

from trader_mcp.adapters import envelope_to_mcp_result
from trader_research.contracts import SideEffect, error_envelope, success_envelope


def test_successful_envelope_converts_to_mcp_result() -> None:
    envelope = success_envelope(
        command="data_get_inventory",
        side_effect=SideEffect.READ_ONLY,
        data={"dataset_id": "dataset_demo"},
    )

    result = envelope_to_mcp_result(envelope)

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

    result = envelope_to_mcp_result(envelope)

    assert result["isError"] is True
    assert result["structuredContent"]["ok"] is False
    assert result["structuredContent"]["errors"] == [{"code": "missing_data", "message": "No bars found."}]


def test_mcp_result_contains_only_json_native_values() -> None:
    envelope = success_envelope(
        command="data_get_inventory",
        side_effect=SideEffect.READ_ONLY,
        data={"symbols": ("DEMO",)},
    )
    result = envelope_to_mcp_result(envelope)

    serialized = json.dumps(result, sort_keys=True)
    parsed = json.loads(serialized)

    assert parsed["structuredContent"]["data"] == {"symbols": ["DEMO"]}
