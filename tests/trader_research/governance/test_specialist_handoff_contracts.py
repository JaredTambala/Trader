"""Contract tests for bounded specialist requests and evidence handoffs.

Subject: Governance values exchanged between the research coordinator and bounded specialists.
Level: In-process contract.
Collaborators: Real handoff and identity value objects; no agents, tools, persistence, or external service.
Guarantees: Requests and handoffs are bounded, JSON-safe, correctly attributed, and domain-authorized.
Non-goals: Routing a specialist, reading canonical evidence, deciding a next action, or persisting a handoff.
"""

from __future__ import annotations

import json

import pytest

from trader_research.foundation import stable_research_id
from trader_research.governance.artifacts import DATA_QUALITY_REPORT, DATASET_MANIFEST
from trader_research.governance.handoffs import (
    BoundedResearchRequest,
    DataRequirement,
    ResearchIssue,
    SpecialistHandoff,
)


def _data_requirement() -> DataRequirement:
    return DataRequirement(
        symbols=("DEMO",),
        asset_class="stocks",
        timeframe="1Min",
        start="2026-01-20T12:00:00Z",
        end="2026-01-20T12:11:00Z",
    )


def test_research_request_and_handoff_round_trip_json() -> None:
    """A valid request and specialist handoff round-trip without losing attribution or warnings."""
    request = BoundedResearchRequest(
        request_id=stable_research_id("research_request", {"objective": "demo"}),
        objective="Evaluate a demo strategy.",
        data_requirement=_data_requirement(),
    )
    warning = ResearchIssue(code="data_agent_warning", message="Partial coverage.")
    handoff = SpecialistHandoff(
        handoff_id="handoff_demo",
        domain_owner="Data",
        producer_tool="data_get_inventory",
        requested_by=request.request_id,
        actor="Data Agent",
        artifact_type=DATASET_MANIFEST,
        payload={
            "dataset_id": "dataset_demo",
            "symbols": ["DEMO"],
            "asset_class": "stocks",
            "timeframe": "1Min",
            "requested_window": {
                "start": "2026-01-20T12:00:00Z",
                "end": "2026-01-20T12:11:00Z",
            },
            "complete": True,
        },
        source_request=request.data_requirement.to_dict(),
        provenance_refs={"envelope_id": "env_demo"},
        warnings=(warning,),
    )

    request_payload = request.to_dict()
    handoff_payload = handoff.to_dict()

    assert (
        BoundedResearchRequest.from_dict(request_payload).to_dict() == request_payload
    )
    assert SpecialistHandoff.from_dict(handoff_payload).to_dict() == handoff_payload
    assert handoff_payload["domain_owner"] == "Data"
    assert handoff_payload["producer_tool"] == "data_get_inventory"
    assert handoff_payload["requested_by"] == request.request_id
    assert handoff_payload["actor"] == "Data Agent"
    assert "agent_owner" not in handoff_payload
    assert "artifact_path" not in handoff_payload
    assert handoff_payload["warnings"] == [
        {"code": "data_agent_warning", "message": "Partial coverage.", "details": {}}
    ]
    json.dumps({"request": request_payload, "handoff": handoff_payload})


def test_domain_validation_rejects_missing_bounds_and_bad_handoffs() -> None:
    """Malformed bounds, ownership, types, and URIs fail before a handoff can propagate."""
    with pytest.raises(ValueError, match="symbols are required"):
        DataRequirement(
            symbols=(), asset_class="stocks", timeframe="1Min", start="s", end="e"
        )
    with pytest.raises(ValueError, match="domain_owner is required"):
        SpecialistHandoff(
            handoff_id="handoff",
            domain_owner="",
            producer_tool="data_get_inventory",
            requested_by="request_demo",
            actor="Data Agent",
            artifact_type=DATASET_MANIFEST,
            payload={"ok": True},
        )
    with pytest.raises(ValueError, match="unsupported artifact type"):
        SpecialistHandoff(
            handoff_id="handoff",
            domain_owner="Data",
            producer_tool="data_get_inventory",
            requested_by="request_demo",
            actor="Data Agent",
            artifact_type="raw_bars",
            payload={"ok": True},
        )
    with pytest.raises(ValueError, match="must be owned by the Data domain"):
        SpecialistHandoff(
            handoff_id="handoff",
            domain_owner="Experiments",
            producer_tool="data_summarize_quality",
            requested_by="request_demo",
            actor="Quant Research Supervisor Agent",
            artifact_type=DATA_QUALITY_REPORT,
            payload={"complete": True},
        )
    with pytest.raises(ValueError, match="artifact_uri type backtest_run"):
        SpecialistHandoff(
            handoff_id="handoff",
            domain_owner="Data",
            producer_tool="data_get_inventory",
            requested_by="request_demo",
            actor="Data Agent",
            artifact_type=DATASET_MANIFEST,
            artifact_uri="research://postgres/backtest_run/run_demo",
        )
