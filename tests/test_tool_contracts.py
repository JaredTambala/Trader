from __future__ import annotations

import json
from datetime import datetime, timezone

from trader.tools.contracts import SideEffect, ToolEnvelope, envelope_json, success_envelope


def test_tool_envelope_is_stable_json() -> None:
    envelope = ToolEnvelope(
        ok=True,
        command="demo",
        side_effect=SideEffect.READ_ONLY,
        generated_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        data={"path": "artifact.json"},
    )

    payload = json.loads(envelope_json(envelope))

    assert payload == {
        "artifacts": {},
        "command": "demo",
        "data": {"path": "artifact.json"},
        "errors": [],
        "generated_at": "2026-01-01T00:00:00+00:00",
        "ok": True,
        "schema_version": "1",
        "side_effect": "read_only",
        "warnings": [],
    }


def test_success_envelope_declares_side_effect_class() -> None:
    envelope = success_envelope(
        command="prepare_paper_promotion",
        side_effect=SideEffect.LOCAL_MUTATING,
        data={"starts_trading": False},
    )

    assert envelope.to_dict()["side_effect"] == "local_mutating"
    assert envelope.to_dict()["data"]["starts_trading"] is False
