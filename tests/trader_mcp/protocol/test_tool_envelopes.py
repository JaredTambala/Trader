"""Contract tests for stable public MCP tool envelopes.

Subject: Serialization and side-effect metadata of the MCP transport envelope.
Level: Contract.
Collaborators: Real protocol value objects with fixed timestamps and payloads.
Guarantees: Wire JSON and declared side effects remain explicit and stable.
Non-goals: MCP result conversion, tool registration, transport processes, or capability behavior.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

from trader_mcp.protocol.contracts import (
    SideEffect,
    ToolEnvelope,
    envelope_json,
    success_envelope,
)


def test_tool_envelope_is_stable_json() -> None:
    """Serialize every public envelope field to one stable JSON shape."""
    envelope = ToolEnvelope(
        ok=True,
        command="data_get_inventory",
        agent_owner="Data Agent",
        side_effect=SideEffect.READ_ONLY,
        generated_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        data={"path": "artifact.json"},
    )

    payload = json.loads(envelope_json(envelope))

    assert payload == {
        "agent_owner": "Data Agent",
        "artifacts": {},
        "command": "data_get_inventory",
        "data": {"path": "artifact.json"},
        "errors": [],
        "generated_at": "2026-01-01T00:00:00+00:00",
        "ok": True,
        "schema_version": "1",
        "side_effect": "read_only",
        "warnings": [],
    }


def test_success_envelope_declares_side_effect_class() -> None:
    """Retain owner and side-effect classification on successful transport envelopes."""
    envelope = success_envelope(
        command="prepare_paper_promotion",
        agent_owner="Quant Research Supervisor Agent",
        side_effect=SideEffect.LOCAL_MUTATING,
        data={"starts_trading": False},
    )

    assert envelope.agent_owner == "Quant Research Supervisor Agent"
    assert envelope.to_dict()["side_effect"] == "local_mutating"
    assert envelope.to_dict()["data"]["starts_trading"] is False
