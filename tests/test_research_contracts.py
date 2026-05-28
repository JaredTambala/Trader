from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from trader_research.contracts import (
    ArtifactReference,
    SideEffect,
    ToolEnvelope,
    envelope_json,
    error_envelope,
    success_envelope,
)


def test_tool_envelope_includes_agent_owner_in_stable_json() -> None:
    envelope = ToolEnvelope(
        ok=True,
        command="data_get_inventory",
        agent_owner="Data Agent",
        side_effect=SideEffect.READ_ONLY,
        generated_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        data={"dataset_id": "dataset_demo"},
    )

    payload = json.loads(envelope_json(envelope))

    assert payload == {
        "agent_owner": "Data Agent",
        "artifacts": {},
        "command": "data_get_inventory",
        "data": {"dataset_id": "dataset_demo"},
        "errors": [],
        "generated_at": "2026-01-01T00:00:00+00:00",
        "ok": True,
        "schema_version": "1",
        "side_effect": "read_only",
        "warnings": [],
    }


def test_success_envelope_derives_data_agent_owner() -> None:
    envelope = success_envelope(
        command="data_get_inventory",
        side_effect=SideEffect.READ_ONLY,
        data={"symbols": ["DEMO"]},
    )

    assert envelope.agent_owner == "Data Agent"
    assert envelope.to_dict()["agent_owner"] == "Data Agent"


def test_error_envelope_preserves_structured_errors() -> None:
    envelope = error_envelope(
        command="data_get_inventory",
        side_effect=SideEffect.READ_ONLY,
        code="missing_data",
        message="No bars found for DEMO.",
        data={"symbol": "DEMO"},
    )

    payload = envelope.to_dict()

    assert payload["ok"] is False
    assert payload["agent_owner"] == "Data Agent"
    assert payload["errors"] == [{"code": "missing_data", "message": "No bars found for DEMO."}]
    assert payload["data"] == {"symbol": "DEMO"}


def test_artifact_reference_serializes_json_safe_values(tmp_path: Path) -> None:
    report_path = tmp_path / "dataset_manifest.json"
    reference = ArtifactReference(
        artifact_type="dataset_manifest",
        path=report_path,
        uri="file://dataset_manifest.json",
        metadata={"created_at": datetime(2026, 1, 1, tzinfo=timezone.utc)},
    )
    envelope = success_envelope(
        command="data_get_inventory",
        side_effect=SideEffect.READ_ONLY,
        artifacts={"dataset_manifest": reference},
    )

    payload = envelope.to_dict()

    assert payload["artifacts"]["dataset_manifest"] == {
        "artifact_type": "dataset_manifest",
        "path": str(report_path),
        "uri": "file://dataset_manifest.json",
        "metadata": {"created_at": "2026-01-01T00:00:00+00:00"},
    }
    json.dumps(payload)


def test_unknown_command_requires_explicit_agent_owner() -> None:
    with pytest.raises(KeyError, match="Unknown research tool"):
        success_envelope(command="mcp_health", side_effect=SideEffect.READ_ONLY)

    envelope = success_envelope(
        command="mcp_health",
        agent_owner="MCP Server",
        side_effect=SideEffect.READ_ONLY,
    )

    assert envelope.agent_owner == "MCP Server"
